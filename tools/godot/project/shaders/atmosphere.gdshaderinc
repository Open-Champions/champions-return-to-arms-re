// atmosphere.gdshaderinc - the sky and the haze of scene mode: what Godot adds above and beyond what
// the game drew for a camera that looked down.
//
// The game has a clear colour per level and, in 19 of 111 levels, a painted dome round the camera that
// ends 18 degrees above the horizon (or is a hemisphere); it has no fog.  Seen along the ground that is a
// flat colour to the zenith, a hard seam where the dome ends, and a world that stops at a cut edge
// (docs/issues/native-first-person-world.md).  Here:
//   rta_sky(direction)        the colour of the sky in a direction of the world (z up).  Round the horizon
//                             it is a ring of colours (rta_sky_ring: 256 directions; row 0 the colours of
//                             the dome's upper edge as the game drew it - or the level's clear colour made
//                             into a horizon - row 1 those of its lower edge), rising to rta_sky_zenith above
//                             the upper edge and falling to rta_sky_ground below the lower one, with a glow
//                             round the sun.  The dome itself is still drawn by the game, over this: the
//                             sky continues it, so the seam is the same colour on both sides.
//   rta_haze(distance, z)     how much of a surface is lost in the haze: nothing near, all of it where
//                             the level's cells end (the game draws 1300 to 1800 units ahead), more low
//                             down than high up.  Its colour is the sky's at the horizon in that direction,
//                             so far ground goes into the sky it stands against.
// All colours are stored values (0..1 of 255), as the game's are.  The values are global shader
// parameters set by project/scene_view.gd once per frame from the level that is running (the clear
// colour and the dome are read from the game while it runs; nothing of it is in this file).

global uniform sampler2D rta_sky_ring : filter_linear, repeat_enable;
global uniform vec4 rta_sky_zenith;     // rgb; a: elevation of the ring's upper edge, radians
global uniform vec4 rta_sky_ground;     // rgb; a: elevation of its lower edge, radians
global uniform vec4 rta_sky_sun;        // xyz: the direction TO the sun; w: strength of its glow (0: none)
global uniform vec4 rta_sky_sun_colour; // rgb; a: 1 = stars (a dark sky gets a few)
global uniform vec4 rta_fog_range;      // distance where it starts, where it is complete, the height it lies at (world z), its thickness
global uniform vec4 rta_fog_amount;     // x: 0..1 how much there is at all; y: how much of it follows the height; z: the share the sky's own colour has in it
global uniform vec4 rta_fog_colour;     // rgb: the haze's own colour (mixed with the sky's at the horizon by rta_fog_amount.z)
global uniform vec4 rta_light_ambient;  // rgb: what arrives of a surface's colour where the sun does not (the game's colour x this)

float rta_hash(vec2 p) {
	vec3 q = fract(vec3(p.xyx) * 0.1031);
	q += dot(q, q.yzx + 33.33);
	return fract((q.x + q.y) * q.z);
}

vec3 rta_ring(vec3 d, float row) {
	float az = atan(d.y, d.x) * (0.5 / PI) + 0.5;
	return textureLod(rta_sky_ring, vec2(az, row), 0.0).rgb;
}

vec3 rta_sky(vec3 d) {
	float e = asin(clamp(d.z, -1.0, 1.0));
	float top = rta_sky_zenith.a, bottom = rta_sky_ground.a;
	vec3 c;
	if (e >= bottom) {
		vec3 ring = rta_ring(d, 0.25);
		// from the ring's upper edge to the zenith: most of the change low down, as a real sky has it
		float t = clamp((e - top) / max(0.5 * PI - top, 0.01), 0.0, 1.0);
		c = mix(ring, rta_sky_zenith.rgb, 1.0 - pow(1.0 - t, 2.6));
		if (rta_sky_sun.w > 0.0) {
			float s = max(dot(d, rta_sky_sun.xyz), 0.0);
			float above = smoothstep(top - 0.02, top + 0.10, e);
			c += rta_sky_sun_colour.rgb * rta_sky_sun.w * above * (0.55 * pow(s, 320.0) + 0.22 * pow(s, 24.0) + 0.10 * pow(s, 4.0));
		}
		if (rta_sky_sun_colour.a > 0.5 && t > 0.0) {
			// a dark sky: a few faint stars, fixed in the world
			vec3 p = d / max(abs(d.z) + 0.35, 0.35);
			vec2 cell = floor(p.xy * 90.0);
			float h = rta_hash(cell);
			vec2 at = fract(p.xy * 90.0) - 0.5 - (vec2(rta_hash(cell + 7.3), rta_hash(cell + 3.1)) - 0.5) * 0.7;
			c += vec3(0.75, 0.80, 1.0) * step(0.965, h) * smoothstep(0.012, 0.0, dot(at, at)) * (h - 0.965) * 22.0 * smoothstep(0.0, 0.25, t);
		}
	} else {
		vec3 ring = rta_ring(d, 0.75);
		float t = clamp((bottom - e) / max(bottom + 0.5 * PI, 0.01), 0.0, 1.0);
		c = mix(ring, rta_sky_ground.rgb, 1.0 - pow(1.0 - t, 3.0));
	}
	return clamp(c, 0.0, 1.0);
}

// The haze between the eye and a surface `dist` away that lies at world height `z`.
float rta_haze(float dist, float z) {
	float x = clamp((dist - rta_fog_range.x) / max(rta_fog_range.y - rta_fog_range.x, 1.0), 0.0, 1.0);
	float depth = 1.0 - exp(-3.2 * x * x);
	float low = exp(-max(z - rta_fog_range.z, 0.0) / max(rta_fog_range.w, 1.0));
	float f = depth * mix(1.0, low, rta_fog_amount.y);
	// whatever its height, the world ends in it: complete over the last tenth of the distance
	f = max(f, smoothstep(0.86, 1.0, x));
	return clamp(f * rta_fog_amount.x, 0.0, 1.0);
}

vec3 rta_haze_colour(vec3 d) {
	vec3 flat_dir = vec3(d.xy, 0.0);
	return mix(rta_fog_colour.rgb, rta_ring(flat_dir, 0.25), rta_fog_amount.z);
}
