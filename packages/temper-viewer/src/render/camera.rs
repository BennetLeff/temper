use temper_viewer_core::transform::Camera;
use wgpu::{BindGroup, BindGroupLayout, Buffer, Device};

pub struct CameraUniform {
    pub view_proj: [[f32; 4]; 4],
}

impl CameraUniform {
    pub fn new() -> Self {
        Self { view_proj: glam::Mat4::IDENTITY.to_cols_array_2d() }
    }

    pub fn update(&mut self, camera: &Camera) {
        let left = camera.center.x - camera.viewport_width / (2.0 * camera.zoom);
        let right = camera.center.x + camera.viewport_width / (2.0 * camera.zoom);
        let bottom = camera.center.y - camera.viewport_height / (2.0 * camera.zoom);
        let top = camera.center.y + camera.viewport_height / (2.0 * camera.zoom);

        let proj = glam::Mat4::orthographic_rh(left, right, bottom, top, -1.0, 1.0);
        self.view_proj = proj.to_cols_array_2d();
    }
}

pub fn create_camera_bind_group_layout(device: &Device) -> BindGroupLayout {
    device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
        label: Some("camera_bind_group_layout"),
        entries: &[wgpu::BindGroupLayoutEntry {
            binding: 0,
            visibility: wgpu::ShaderStages::VERTEX,
            ty: wgpu::BindingType::Buffer {
                ty: wgpu::BufferBindingType::Uniform,
                has_dynamic_offset: false,
                min_binding_size: None,
            },
            count: None,
        }],
    })
}

pub fn create_camera_buffer(device: &Device) -> Buffer {
    device.create_buffer(&wgpu::BufferDescriptor {
        label: Some("camera_uniform_buffer"),
        size: std::mem::size_of::<[[f32; 4]; 4]>() as u64,
        usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
        mapped_at_creation: false,
    })
}

pub fn create_camera_bind_group(
    device: &Device,
    layout: &BindGroupLayout,
    buffer: &Buffer,
) -> BindGroup {
    device.create_bind_group(&wgpu::BindGroupDescriptor {
        label: Some("camera_bind_group"),
        layout,
        entries: &[wgpu::BindGroupEntry {
            binding: 0,
            resource: buffer.as_entire_binding(),
        }],
    })
}
