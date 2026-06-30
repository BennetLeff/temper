// Line and point rendering shader with camera uniform
struct CameraUniform {
    view_proj: mat4x4<f32>,
};

@group(0) @binding(0)
var<uniform> camera: CameraUniform;

struct VertexInput {
    @location(0) position: vec2<f32>,
    @location(1) color: vec4<f32>,
};

struct PointInput {
    @location(0) position: vec2<f32>,
    @location(1) color: vec4<f32>,
    @location(2) size: f32,
};

struct InstancedInput {
    @location(0) position: vec2<f32>,
    @location(1) uv: vec2<f32>,
    @location(2) model_col_0: vec4<f32>,
    @location(3) model_col_1: vec4<f32>,
    @location(4) model_col_2: vec4<f32>,
    @location(5) model_col_3: vec4<f32>,
    @location(6) color: vec4<f32>,
    @location(7) highlight: u32,
};

struct VertexOutput {
    @builtin(position) clip_position: vec4<f32>,
    @location(0) color: vec4<f32>,
    @location(1) @interpolate(flat) highlight: u32,
};

// Line rendering
@vertex
fn vs_main(in: VertexInput) -> VertexOutput {
    var out: VertexOutput;
    out.clip_position = camera.view_proj * vec4<f32>(in.position, 0.0, 1.0);
    out.color = in.color;
    out.highlight = 0u;
    return out;
}

// Point rendering (grid dots)
@vertex
fn vs_main_point(in: PointInput) -> VertexOutput {
    var out: VertexOutput;
    var p = in.position;
    out.clip_position = camera.view_proj * vec4<f32>(p.x - in.size * 0.5, p.y - in.size * 0.5, 0.0, 1.0);
    out.color = in.color;
    out.highlight = 0u;
    return out;
}

// Instanced component rendering
@vertex
fn vs_main_instanced(in: InstancedInput) -> VertexOutput {
    var out: VertexOutput;
    var model = mat4x4<f32>(
        in.model_col_0, in.model_col_1, in.model_col_2, in.model_col_3,
    );
    var world = model * vec4<f32>(in.position, 0.0, 1.0);
    out.clip_position = camera.view_proj * world;
    out.color = in.color;
    out.highlight = in.highlight;
    return out;
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    return in.color;
}

// Instanced fragment with highlight pulse
@fragment
fn fs_main_instanced(in: VertexOutput) -> @location(0) vec4<f32> {
    if (in.highlight == 1u) {
        var pulse = in.color;
        pulse.r = clamp(pulse.r * 1.5, 0.0, 1.0);
        pulse.g = clamp(pulse.g * 1.5, 0.0, 1.0);
        pulse.b = clamp(pulse.b * 1.5, 0.0, 1.0);
        return pulse;
    }
    return in.color;
}
