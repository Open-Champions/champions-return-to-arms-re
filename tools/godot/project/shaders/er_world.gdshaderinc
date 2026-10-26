// er_world.gdshaderinc - the Elden Ring world layer on the level's pieces (GS_ER; look.er_world, er_world.gd, rta_world.cpp).
//
// A piece of the level whose texture reads as a material class (er_class, and er_class_b where a second class covers part
// of it - a path through grass) keeps its texture's own colour at a coarse scale (the level's painted light, its tint,
// what lies where) and takes its fine detail from the owner's own Elden Ring material of that class: albedo and normal
// layers of two texture arrays (rta_er_albedo, rta_er_normal; one layer per class), mapped in world space at a real scale
// (one repeat every rta_er_scale units: a character is about 65 units tall) from the three axes (triplanar: no stretched
// texture on a cliff, no seam where two of the game's textures meet), with a second, larger repeat over it that breaks
// the tiling.  Per pixel the texel's own colour says which of the two classes it is (er_member, as rta_world.cpp reads
// whole textures).  The relief of the normal map turns the pixel toward or away from the level's light.  Far off, the
// detail gives way to the texture as it is (no shimmer).
//
// Classes: 1 grass, 2 dirt, 3 stone, 4 cobble, 5 wood, 6 metal, 7 sand, 8 snow (layers 0..7).

uniform int er_class = 0;
uniform int er_class_b = 0;
uniform int er_class2 = 0;          // a fused pair (GS_FUSED): the first pass's
uniform int er_class2_b = 0;
global uniform vec4 rta_er;         // x strength (0 off .. 1), y relief, z distance where the detail is gone, w large repeat share
global uniform vec4 rta_er_scale_a; // units per repeat: grass, dirt, stone, cobble
global uniform vec4 rta_er_scale_b; //                   wood, metal, sand, snow
global uniform vec4 rta_er_keep_a;  // how much of the game's own fine detail stays, per class (0 none .. 1 all)
global uniform vec4 rta_er_keep_b;
global uniform vec4 rta_er_amount_a; // how strong the material's detail is, per class (0 none .. 1 as it is)
global uniform vec4 rta_er_amount_b;
global uniform vec4 rta_er_reader;    // x: where grass's band of hues starts (degrees)
global uniform sampler2DArray rta_er_albedo : filter_linear_mipmap_anisotropic, repeat_enable;
global uniform sampler2DArray rta_er_normal : filter_linear_mipmap_anisotropic, repeat_enable;

varying vec3 v_er_normal;           // the game's normal, world space (zero: none)

float er_smooth(float a, float b, float x) { return smoothstep(a, b, x); }
float er_band(float h, float lo, float hi, float soft) { return er_smooth(lo - soft, lo, h) * (1.0 - er_smooth(hi, hi + soft, h)); }

// the membership of a colour (0..1, stored values) in a class's family - as member() in rta_world.cpp
float er_member(int cls, vec3 c) {
	float mx = max(c.r, max(c.g, c.b)), mn = min(c.r, min(c.g, c.b));
	float lum = dot(c, vec3(0.3, 0.59, 0.11));
	float sat = (mx - mn) / max(mx, 0.04);
	float h = 0.0;
	if (mx - mn > 1e-4) {
		if (mx == c.r) h = 60.0 * mod((c.g - c.b) / (mx - mn) + 6.0, 6.0);
		else if (mx == c.g) h = 60.0 * ((c.b - c.r) / (mx - mn) + 2.0);
		else h = 60.0 * ((c.r - c.g) / (mx - mn) + 4.0);
	}
	float coloured = er_smooth(0.06, 0.16, sat);
	float snow = er_smooth(0.62, 0.78, lum) * (1.0 - er_smooth(0.10, 0.22, sat));
	float sand = er_band(h, 26.0, 58.0, 10.0) * coloured * (1.0 - er_smooth(0.55, 0.75, sat)) * er_smooth(0.42, 0.56, lum);
	if (cls == 1) return er_band(h, rta_er_reader.x, 170.0, 16.0) * er_smooth(0.08, 0.18, sat);
	if (cls == 2 || cls == 5) return er_band(h, 6.0, 56.0, 10.0) * coloured * (1.0 - sand);
	if (cls == 7) return sand;
	if (cls == 8) return snow;
	return (1.0 - coloured) * (1.0 - snow);     // stone, cobble, metal
}

float er_scale(int cls) {
	return cls <= 4 ? rta_er_scale_a[cls - 1] : rta_er_scale_b[cls - 5];
}

float er_keep(int cls) {
	return cls <= 4 ? rta_er_keep_a[cls - 1] : rta_er_keep_b[cls - 5];
}

float er_amount(int cls) {
	return cls <= 4 ? rta_er_amount_a[cls - 1] : rta_er_amount_b[cls - 5];
}

// the class's albedo (stored values, 0..1) divided by its own mean - the fine detail as a factor - and its normal
// (world space), triplanar at world position p with world normal n
vec3 er_sample(int cls, vec3 p, vec3 dpx, vec3 dpy, vec3 n, vec3 w, out vec3 bent) {
	float layer = float(cls - 1);
	float s = 1.0 / er_scale(cls);
	vec2 uz = p.xy * s, ux = p.yz * s, uy = p.xz * s;
	vec2 dzx = dpx.xy * s, dzy = dpy.xy * s, dxx = dpx.yz * s, dxy = dpy.yz * s, dyx = dpx.xz * s, dyy = dpy.xz * s;
	vec3 a = vec3(0.0);
	vec3 tn = vec3(0.0);
	// the ground's own projection (most of a level), and the walls' only where they are walls
	if (w.z > 0.0) {
		a += textureGrad(rta_er_albedo, vec3(uz, layer), dzx, dzy).rgb * w.z;
		vec2 nz = textureGrad(rta_er_normal, vec3(uz, layer), dzx, dzy).rg * 2.0 - 1.0;
		tn += vec3(nz.x, nz.y, 0.0) * w.z;
	}
	if (w.x > 0.0) {
		a += textureGrad(rta_er_albedo, vec3(ux, layer), dxx, dxy).rgb * w.x;
		vec2 nx = textureGrad(rta_er_normal, vec3(ux, layer), dxx, dxy).rg * 2.0 - 1.0;
		tn += vec3(0.0, nx.x, nx.y) * w.x;
	}
	if (w.y > 0.0) {
		a += textureGrad(rta_er_albedo, vec3(uy, layer), dyx, dyy).rgb * w.y;
		vec2 ny = textureGrad(rta_er_normal, vec3(uy, layer), dyx, dyy).rg * 2.0 - 1.0;
		tn += vec3(ny.x, 0.0, ny.y) * w.y;
	}
	// a second repeat, 3.7 times larger and turned, over the first: no visible tiling across a field
	if (rta_er.w > 0.0 && w.z > 0.0) {
		mat2 turn = mat2(vec2(0.8, 0.6), vec2(-0.6, 0.8));
		vec3 b = textureGrad(rta_er_albedo, vec3(turn * uz * 0.27, layer), turn * dzx * 0.27, turn * dzy * 0.27).rgb;
		a = mix(a, a * (b / max(textureLod(rta_er_albedo, vec3(0.5, 0.5, layer), 14.0).rgb, vec3(0.02))), rta_er.w * w.z);
	}
	vec3 mean = max(textureLod(rta_er_albedo, vec3(0.5, 0.5, layer), 14.0).rgb, vec3(0.03));
	float amount = er_amount(cls);
	bent = tn * amount;
	return mix(vec3(1.0), clamp(a / mean, vec3(0.2), vec3(2.6)), amount);
}

// the texel of a level piece (0..255, stored values) with the class's detail in place of its own; `low` is the texture
// read a few mip levels coarser (its colour where the detail is), `tint` the vertex light (1 = 128), `dist` the distance
// from the eye.  `relief` gets the
// factor the normal map's relief gives under the level's light (1: none)
vec3 er_apply(int cls, int cls_b, vec3 texel, vec3 low, vec3 tint, vec3 p, vec3 n, float dist, out float relief) {
	relief = 1.0;
	vec3 dpx = dFdx(p), dpy = dFdy(p);       // (before any branch that is not the same for every pixel)
	if (rta_er.x < 0.0) {
		// (test aid, look.er_world_strength < 0: each class in a colour of its own over the texel's brightness; the second
		// class where the texel reads as it, striped)
		const vec3 K[9] = vec3[9](vec3(1.0), vec3(0.2, 0.9, 0.2), vec3(0.6, 0.35, 0.1), vec3(0.6), vec3(0.2, 0.4, 1.0), vec3(1.0, 0.6, 0.1),
				vec3(0.9, 0.2, 0.9), vec3(1.0, 0.9, 0.3), vec3(0.8, 1.0, 1.0));
		vec3 lc = clamp(low / 255.0 * tint, 0.0, 1.0);
		int shown = cls;
		if (cls_b > 0 && er_member(cls_b, lc) > er_member(cls, lc) && mod(floor(p.x * 0.1 + p.y * 0.1), 2.0) < 1.0) shown = cls_b;
		return K[clamp(shown, 0, 8)] * (60.0 + dot(texel, vec3(0.3, 0.59, 0.11)));
	}
	float strength = rta_er.x * (1.0 - er_smooth(rta_er.z * 0.55, rta_er.z, dist));
	if (strength <= 0.0 || cls <= 0) return texel;
	vec3 w = pow(abs(n), vec3(6.0));
	w /= max(w.x + w.y + w.z, 1e-4);
	w = max(w - 0.04, 0.0);
	w /= max(w.x + w.y + w.z, 1e-4);
	vec3 bent_a;
	vec3 f = er_sample(cls, p, dpx, dpy, n, w, bent_a);
	float keep = er_keep(cls);
	vec3 bent = bent_a;
	if (cls_b > 0) {
		vec3 lc = clamp(low / 255.0 * tint, 0.0, 1.0);     // as the draw shows it: with the game's vertex light
		float ma = er_member(cls, lc), mb = er_member(cls_b, lc);
		float t = er_smooth(0.3, 0.7, mb / max(ma + mb, 1e-3));
		if (t > 0.001) {
			vec3 bent_b;
			vec3 fb = er_sample(cls_b, p, dpx, dpy, n, w, bent_b);
			f = mix(f, fb, t);
			bent = mix(bent_a, bent_b, t);
			keep = mix(keep, er_keep(cls_b), t);
		}
	}
	// ground that stands up as a wall (a bank, a cliff, a cave's side) is rock, whatever its colour: grass, dirt, sand and
	// snow give way to stone where the surface is steep
	if (cls == 1 || cls == 2 || cls == 7 || cls == 8) {
		float steep = er_smooth(0.62, 0.32, abs(n.z));
		if (steep > 0.001) {
			vec3 bent_s;
			vec3 fs = er_sample(3, p, dpx, dpy, n, w, bent_s);
			f = mix(f, fs, steep);
			bent = mix(bent, bent_s, steep);
			keep = mix(keep, er_keep(3), steep);
		}
	}
	// the material's detail over the game's texture: as much of the game's own detail as `keep` says (its painted designs,
	// cracks, carvings), the rest of it the texture's colour where the detail is
	vec3 detail = mix(low, texel, keep) * f;
	// the relief: the normal bent by the map, against the level's light (the game lit its textures from there)
	vec3 nb = normalize(n + bent * rta_er.y);
	vec3 sun = normalize(rta_sky_sun.xyz);
	relief = mix(1.0, clamp(1.0 + 0.9 * (dot(nb, sun) - dot(n, sun)), 0.55, 1.45), strength);
	return mix(texel, clamp(detail, vec3(0.0), vec3(255.0)), strength);
}
