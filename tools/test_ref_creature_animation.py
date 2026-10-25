"""Authored synthetic integration fixtures; no ELF, extracted model or game bytes."""
import unittest
from fractions import Fraction as Q
import ref_core as C
import ref_anim as A
import ref_creature as R
import ref_creature_animation as V
import ref_monsters_1 as M


class Binding(unittest.TestCase):
    def test_resources_and_signed_this(self):
        m = R.Memory()
        for p,v in ((0x1024,0x2000),(0x200c,0x3000),(0x2014,0x4000),
                    (0x1048,0x5000),(0x5000+27*8,0xfff0),(0x5004+27*8,0x6000)):
            m.poke(p,4,v)
        self.assertEqual(V.class_resource(m,0x1000,1),0x3000)
        self.assertEqual(V.class_resource(m,0x1000,2),0x4000)
        self.assertEqual(V.virtual_target(m,0x1000,27),(0x6000,0xff0))
        m.poke(0x2000,4,0x7000)
        self.assertEqual(V.role_lump(m,0x1000,False),0x7000)
        self.assertEqual(V.role_lump(m,0x1000,True),0x13c8)

    def test_explicit_role_failure_does_not_fall_back(self):
        log=[]
        def prop(k):
            log.append(('prop',k))
            return b'missing' if k==b'idlename' else b'actor'
        def find(l,n):
            log.append(('find',l,n))
            return 0
        self.assertEqual(V.find_role_anim(7,b'idle',prop,find),0)
        self.assertEqual(log,[('prop',b'idlename'),('prop',b'idlename'),
                              ('find',7,b'missing.anm')])

    def test_named_then_generic_and_empty_override(self):
        log=[]
        def find(l,n):
            log.append(n)
            return 5 if n==b'idle.anm' else 0
        self.assertEqual(V.find_role_anim(7,b'idle',lambda k:
                         b'actor' if k==b'name' else None,find),5)
        self.assertEqual(log,[b'actor_idle.anm',b'idle.anm'])
        log.clear()
        V.find_role_anim(7,b'idle',lambda k:b'',find)
        self.assertEqual(log,[b'.anm'])

    def test_role_scratch_host_limit(self):
        with self.assertRaises(ValueError):
            V.find_role_anim(0,b'a'*156,lambda k:None,lambda l,n:0)

    def test_shared_event_byte_before_raw_seconds(self):
        m=R.Memory(); model=R.Model(m)
        m.poke(0x1024,4,0x2000); m.poke(0x201c,4,0x3000)
        times=[C.f32(x) for x in (0.25,0.5,0.75,1)]
        V.set_class_events(model,0x1000,3,times,[1,2,4,0x108])
        self.assertEqual(model.writes,[(p,n,v) for i in range(4)
            for p,n,v in ((0x3018+8*i,1,1<<i),(0x3014+8*i,4,times[i]))])

    def test_original_class_dispatch_can_drive_owned_animation(self):
        memory=R.Memory(); system=A.AnimSystem(); state=A.AnimState()
        clip=A.Clip(A.encode_clip([((0,0,0),(4096,0,0,0))],10))
        for p,v in ((0x1024,0x2000),(0x203c,0x3000),(0x1048,0x5000),
                    (0x5004+27*8,0x2ab704),(0x1300,100)):
            memory.poke(p,4,v)
        def start(anim,resource,flags,blend):
            self.assertEqual((anim,resource,flags,blend),(0x1114,0x3000,3,0x3e999999))
            A.anim_start(blend,state,clip,flags)
        model=M.Model(memory,{'anim_start':start,'handle_clear':lambda p:0})
        model.vcall(0x1000,27,0)  # real SmallSpider state body, no universal role map
        self.assertIs(state.top().clip,clip)
        self.assertEqual(state.top().flags,3)
        self.assertEqual(model.u16(0x1232),0)
        self.assertEqual(model.u32(0x10f4),220+((0x3c6ef35f>>16)%300))


class PoseToMesh(unittest.TestCase):
    def test_parent_first_bind_correction_and_quantization(self):
        s=A.AnimSystem(); A.vu0_reset_stack(s)
        # Exact 180 degree rotation, nonzero root and child translations.
        root=A.vu0_compose_joint(s,[0,0,A.ONE,0],list(map(C.f32,(10,0,0))),[0,0,0],0)
        child=A.vu0_compose_joint(s,[0,0,0,A.ONE],list(map(C.f32,(2,0,0))),[64,0,0],1)
        self.assertEqual(root,[[-4096,0,0,640],[0,-4096,0,0],[0,0,4096,0]])
        self.assertEqual(child,[[-4096,0,0,448],[0,-4096,0,0],[0,0,4096,0]])
        self.assertEqual(V.skin_point([root,child],[(1,255)],(16,0,0)),(6,0,0))
        # A sibling at depth 1 uses the root, not the previous child's world matrix.
        sibling=A.vu0_compose_joint(s,[0,0,0,A.ONE],list(map(C.f32,(3,0,0))),[0,0,0],1)
        self.assertEqual(sibling[0][3],448)

    def test_quantized_wrap_and_four_weights(self):
        s=A.AnimSystem(); A.vu0_reset_stack(s)
        row=A.vu0_compose_joint(s,[0,0,0,A.ONE],[C.f32(512),0,0],[0,0,0],0)
        self.assertEqual(row[0][3],-32768)
        mats=[[[4096,0,0,64*i],[0,4096,0,0],[0,0,4096,0]] for i in range(4)]
        self.assertEqual(V.skin_point(mats,[(0,64),(1,64),(2,64),(3,63)],(16,0,0)),
                         (Q(636,255),0,0))
        with self.assertRaises(ValueError):
            V.skin_point(mats,[(0,254)],(0,0,0))

    def test_draw_translation_height_offset_and_axis_adapter(self):
        m=R.Memory()
        for off,val in ((0x10,10),(0x14,20),(0x18,999),(0x3c,30),(0xdc,2),(0xe0,3)):
            m.poke(0x1000+off,4,C.f32(val))
        mat=V.creature_draw_matrix(m,0x1000)
        self.assertEqual(list(map(C.to_float,mat[9:])),[13,20,30])
        p=C.mat34_transform_point(mat,[C.f32(1),0,0])
        # The game's quarter-turn cosine approximation is not mathematical zero.
        self.assertEqual(p,[0x414fffff,0x41b00000,0x41f00000])
        self.assertEqual(V.godot_point((13,22,30)),(13,30,-22))

    def test_top_skeleton_and_blend_then_skin(self):
        def clip(x,bind):
            return A.Clip(A.encode_clip([((x,0,0),(4096,0,0,0))],10,bind=[bind]))
        s=A.AnimSystem(); s.draw_frame=10
        state=A.AnimState()
        A.anim_push(state,clip(0,(0,0,0)),0)
        A.anim_push_with_weights(state,clip(128,(64,0,0)),0,C.f32(.5),0,A.ONE,0)
        pose=V.draw_pose(s,state)
        # Local translation blends to 1; TOP clip bind adds 1, even at half weight.
        self.assertEqual(pose.mats[0][0][3],128)
        self.assertEqual(V.skin_point(pose.mats,[(0,255)],(0,0,0)),(2,0,0))
        self.assertEqual(pose.stamp,10)
        self.assertIs(state.pose,pose)

    def test_no_full_base_draws_default(self):
        s=A.AnimSystem(); s.draw_frame=10; state=A.AnimState()
        clip=A.Clip(A.encode_clip([((640,0,0),(4096,0,0,0))],10))
        A.anim_push_with_weights(state,clip,0,C.f32(.5),0,A.ONE,0)
        self.assertIs(V.draw_pose(s,state),s.poses.default)
        self.assertIsNone(state.pose)


if __name__=='__main__':
    unittest.main()
