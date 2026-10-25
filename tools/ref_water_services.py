"""SLUS-20973 v2.00 water services, independently authored addressed contracts.

See docs/spec/water-services.md. Synthetic fixtures only in the accompanying tests.
Raw32 arithmetic uses ref_core; world/tree/chunk/grid state is supplied memory.
Host bounds refuse malformed trees and preserve completed writes. No allocator,
water simulation tick, neighbor propagation or renderer is implied by these bodies.
"""
import ref_core as C
import ref_creature as R

ONE, HALF, F12, F16, F32, F60 = map(C.f32, (1, .5, 12, 16, 32, 60))
G_CUT_SKIP = 0x44FCEC


class WaterFault(ValueError):
    pass


class Model(R.Model):
    node_budget = 65536                 # host termination bound, not game policy

    def query(self, world, lo, hi, capacity, out=None):
        """0x189240-0x189434: water-only BSP query, inclusive box, no dedup.
        capacity includes the terminating null. The original fixed local pointer
        stack holds 16 entries. `out` optionally exposes original output stores.
        Returned Python list is a host representation, not an original return ABI."""
        if capacity < 2:
            raise WaterFault('capacity must include one result and terminator')
        if out is not None:
            self.w32(out, 0)
        result = []
        stack = [self.u32(world+4)]
        visited = 0
        while stack:
            visited += 1
            if visited > self.node_budget:
                raise WaterFault('tree traversal budget')
            node = stack.pop()
            tag = self.u16(node)
            if tag & 0x8000:
                if not tag & 0x4000:
                    continue
                axis = tag & 0xfff
                if axis > 2:
                    raise WaterFault('invalid split axis')
                # Two signed halfword loads and OR, not an ordinary u32 load.
                threshold = lambda off: C.from_int(R.s32(
                    (self.s16(node+off) | (self.s16(node+off+2)<<16)) << 2))
                if C.le(lo[axis], threshold(2)):
                    stack.append(node+20)
                if C.le(threshold(6), hi[axis]):
                    stack.append(node+18+2*self.s16(node+18))
                if len(stack)>16:
                    raise WaterFault('original 16-pointer stack overflow')
                continue
            for i in range(tag):
                chunk = self.u32(world+0x24) + 0x3c*self.u16(node+2+2*i)
                if not self.u32(chunk+0x24) & 0x80:
                    continue
                if any(C.lt(hi[k],self.u32(chunk+8+4*k)) or
                       C.lt(self.u32(chunk+0x14+4*k),lo[k]) for k in range(3)):
                    continue
                if out is not None:
                    self.w32(out+4*len(result),chunk)
                result.append(chunk)
                if len(result)==capacity-1:
                    if out is not None:
                        self.w32(out+4*len(result),0)
                    return result
        if out is not None:
            self.w32(out+4*len(result),0)
        return result

    def water_test(self, radius, world, pos, height_out=0):
        """0x189438-0x189510. First hit only; absent hit preserves heightOut."""
        lo = (C.sub(C.sub(pos[0],radius),ONE),
              C.sub(C.sub(pos[1],radius),ONE),C.sub(pos[2],ONE))
        hi = (C.add(C.add(pos[0],radius),ONE),
              C.add(C.add(pos[1],radius),ONE),C.add(pos[2],F60))
        chunks = self.query(world,lo,hi,2)
        if chunks and height_out:
            self.w32(height_out,self.u32(chunks[0]+0x10))
        return int(bool(chunks))

    def water_disturb(self, strength, radius, world, pos):
        """0x189514-0x189840. Counts hits including duplicates and absent grids.
        Positive radius and positive rounded chunk width are the admitted domain.
        Original visits up to 15 hits; upper-only s16 accumulation clamp."""
        if self.u8(G_CUT_SKIP):
            return 0
        if not C.lt(0,radius):
            raise WaterFault('positive radius required')
        lo = (C.sub(pos[0],radius),C.sub(pos[1],radius),C.sub(pos[2],ONE))
        hi = (C.add(pos[0],radius),C.add(pos[1],radius),C.add(pos[2],F60))
        chunks=self.query(world,lo,hi,16)
        for chunk in chunks:
            grid=self.u32(self.u32(chunk)+8)
            if not grid:
                continue
            width=C.sub(self.u32(chunk+0x14),self.u32(chunk+8))
            extent=C.to_int(C.add(C.mul(width,0x3daaaaaa),HALF))
            if R.s32(extent)<=0:
                raise WaterFault('positive rounded chunk width required')
            inv=C.div(ONE,C.mul(C.from_int(extent),F12))
            def grid_coord(k):
                origin=C.mul(C.from_int(self.s32(chunk+0x28+4*k)),C.f32(.25))
                return C.add(C.mul(C.mul(C.sub(pos[k],origin),F32),inv),F16)
            gx,gy=grid_coord(0),grid_coord(1)
            scaled=C.mul(C.mul(radius,F32),inv)
            r2=C.mul(scaled,scaled)
            factor=C.div(strength,r2)
            # Bounds use the ORIGINAL radius, not the radius in grid coordinates.
            def bounds(g):
                return (max(0,R.s32(C.to_int(C.sub(C.sub(g,radius),ONE)))),
                        min(31,R.s32(C.to_int(C.add(C.add(g,radius),ONE)))))
            xmin,xmax=bounds(gx); ymin,ymax=bounds(gy)
            for x in range(xmin,xmax+1):
                for y in range(ymin,ymax+1):
                    dy=C.sub(C.from_int(y),gy); dx=C.sub(C.from_int(x),gx)
                    d2=C.add(C.mul(dy,dy),C.mul(dx,dx))
                    if C.lt(r2,d2):
                        continue
                    amount=R.s32(C.to_int(C.sub(strength,C.mul(d2,factor))))
                    address=grid+0xa90+2*(32*x+y)
                    value=R.s32(amount+self.s16(address))
                    self.w16(address,min(value,32767))
        return len(chunks)
