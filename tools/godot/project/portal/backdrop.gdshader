shader_type canvas_item;
// backdrop.gdshader - the game's own picture behind the portal, softly blurred and dimmed.
// Reads what has been drawn so far (the game scene underneath) through the screen texture's
// mip chain plus a small ring of samples, so the blur costs a handful of reads.

uniform sampler2D screen : hint_screen_texture, filter_linear_mipmap, repeat_disable;
uniform float amount = 1.0;         // 0: the game as it is ... 1: fully blurred and dimmed
uniform float darken = 0.42;

void fragment() {
	float lod = 3.2 * amount;
	vec2 px = SCREEN_PIXEL_SIZE * 10.0 * amount;
	vec3 sum = textureLod(screen, SCREEN_UV, lod).rgb * 2.0;
	sum += textureLod(screen, SCREEN_UV + vec2(px.x, 0.0), lod).rgb;
	sum += textureLod(screen, SCREEN_UV - vec2(px.x, 0.0), lod).rgb;
	sum += textureLod(screen, SCREEN_UV + vec2(0.0, px.y), lod).rgb;
	sum += textureLod(screen, SCREEN_UV - vec2(0.0, px.y), lod).rgb;
	sum += textureLod(screen, SCREEN_UV + px * 0.7, lod).rgb;
	sum += textureLod(screen, SCREEN_UV - px * 0.7, lod).rgb;
	sum += textureLod(screen, SCREEN_UV + vec2(px.x, -px.y) * 0.7, lod).rgb;
	sum += textureLod(screen, SCREEN_UV + vec2(-px.x, px.y) * 0.7, lod).rgb;
	vec3 col = sum / 10.0;
	float grey = dot(col, vec3(0.299, 0.587, 0.114));
	col = mix(col, vec3(grey), 0.25 * amount);                  // a little colour taken out
	col *= mix(1.0, 1.0 - darken, amount);
	COLOR = vec4(col, 1.0);
}
