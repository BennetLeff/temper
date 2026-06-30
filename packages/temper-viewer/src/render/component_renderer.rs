use temper_viewer_core::model::Component;
use temper_viewer_core::color;
use wgpu::{Device, Queue, RenderPass};
use wgpu::util::DeviceExt;

pub const COMPONENT_INSTANCE_SIZE: u64 = std::mem::size_of::<ComponentInstance>() as u64;

#[repr(C)]
#[derive(Copy, Clone, bytemuck::Pod, bytemuck::Zeroable)]
pub struct ComponentInstance {
    pub transform: [[f32; 4]; 4],
    pub color: [f32; 4],
    pub highlight: u32,
}

pub struct ComponentRenderer {
    pipeline: wgpu::RenderPipeline,
    vertex_buffer: wgpu::Buffer,
    index_buffer: wgpu::Buffer,
    instance_buffer: wgpu::Buffer,
    num_indices: u32,
    num_instances: u32,
}

impl ComponentRenderer {
    pub fn new(
        device: &Device,
        shader: &wgpu::ShaderModule,
        camera_layout: &wgpu::BindGroupLayout,
        format: wgpu::TextureFormat,
    ) -> Self {
        let vertices: [f32; 16] = [
            -0.5, -0.5,  0.0, 0.0,
             0.5, -0.5,  1.0, 0.0,
             0.5,  0.5,  1.0, 1.0,
            -0.5,  0.5,  0.0, 1.0,
        ];
        let indices: [u16; 6] = [0, 1, 2, 0, 2, 3];

        let vertex_buffer = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some("comp_vertex"),
            contents: bytemuck::cast_slice(&vertices),
            usage: wgpu::BufferUsages::VERTEX,
        });
        let index_buffer = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some("comp_index"),
            contents: bytemuck::cast_slice(&indices),
            usage: wgpu::BufferUsages::INDEX,
        });
        let instance_buffer = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("comp_instance"),
            size: COMPONENT_INSTANCE_SIZE * 256,
            usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });

        let layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: Some("comp_layout"),
            bind_group_layouts: &[camera_layout],
            push_constant_ranges: &[],
        });

        let pipeline = device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
            label: Some("comp_pipeline"),
            layout: Some(&layout),
            vertex: wgpu::VertexState {
                module: shader,
                entry_point: Some("vs_main_instanced"),
                buffers: &[
                    wgpu::VertexBufferLayout {
                        array_stride: 16,
                        step_mode: wgpu::VertexStepMode::Vertex,
                        attributes: &[
                            wgpu::VertexAttribute { offset: 0, format: wgpu::VertexFormat::Float32x2, shader_location: 0 },
                            wgpu::VertexAttribute { offset: 8, format: wgpu::VertexFormat::Float32x2, shader_location: 1 },
                        ],
                    },
                    wgpu::VertexBufferLayout {
                        array_stride: COMPONENT_INSTANCE_SIZE,
                        step_mode: wgpu::VertexStepMode::Instance,
                        attributes: &[
                            wgpu::VertexAttribute { offset: 0, format: wgpu::VertexFormat::Float32x4, shader_location: 2 },
                            wgpu::VertexAttribute { offset: 16, format: wgpu::VertexFormat::Float32x4, shader_location: 3 },
                            wgpu::VertexAttribute { offset: 32, format: wgpu::VertexFormat::Float32x4, shader_location: 4 },
                            wgpu::VertexAttribute { offset: 48, format: wgpu::VertexFormat::Float32x4, shader_location: 5 },
                            wgpu::VertexAttribute { offset: 64, format: wgpu::VertexFormat::Float32x4, shader_location: 6 },
                            wgpu::VertexAttribute { offset: 80, format: wgpu::VertexFormat::Uint32, shader_location: 7 },
                        ],
                    },
                ],
                compilation_options: Default::default(),
            },
            fragment: Some(wgpu::FragmentState {
                module: shader,
                entry_point: Some("fs_main_instanced"),
                targets: &[Some(wgpu::ColorTargetState {
                    format,
                    blend: Some(wgpu::BlendState::ALPHA_BLENDING),
                    write_mask: wgpu::ColorWrites::ALL,
                })],
                compilation_options: Default::default(),
            }),
            primitive: wgpu::PrimitiveState {
                topology: wgpu::PrimitiveTopology::TriangleList,
                strip_index_format: None,
                front_face: wgpu::FrontFace::Ccw,
                cull_mode: None,
                polygon_mode: wgpu::PolygonMode::Fill,
                unclipped_depth: false,
                conservative: false,
            },
            multisample: wgpu::MultisampleState::default(),
            multiview: None,
            cache: None,
            depth_stencil: None,
        });

        Self { pipeline, vertex_buffer, index_buffer, instance_buffer, num_indices: 6, num_instances: 0 }
    }

    pub fn update_instances(&mut self, device: &Device, queue: &Queue, components: &[Component]) {
        let instances: Vec<ComponentInstance> = components.iter().map(|c| {
            let cos = c.rotation.to_radians().cos();
            let sin = c.rotation.to_radians().sin();
            let color_arr = color::component_color(c.component_type).to_f32_array();
            ComponentInstance {
                transform: [
                    [c.width * cos, c.width * sin, 0.0, 0.0],
                    [-c.height * sin, c.height * cos, 0.0, 0.0],
                    [0.0, 0.0, 1.0, 0.0],
                    [c.position.x, c.position.y, 0.0, 1.0],
                ],
                color: [color_arr[0], color_arr[1], color_arr[2], 1.0],
                highlight: 0,
            }
        }).collect();

        self.num_instances = instances.len() as u32;
        if self.num_instances == 0 { return; }

        let needed = COMPONENT_INSTANCE_SIZE * instances.len() as u64;
        if needed > self.instance_buffer.size() {
            self.instance_buffer = device.create_buffer(&wgpu::BufferDescriptor {
                label: Some("comp_instance"),
                size: needed,
                usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
                mapped_at_creation: false,
            });
        }
        queue.write_buffer(&self.instance_buffer, 0, bytemuck::cast_slice(&instances));
    }

    pub fn draw<'a>(&'a self, render_pass: &mut RenderPass<'a>, camera_bind_group: &'a wgpu::BindGroup) {
        if self.num_instances == 0 { return; }
        render_pass.set_pipeline(&self.pipeline);
        render_pass.set_bind_group(0, camera_bind_group, &[]);
        render_pass.set_vertex_buffer(0, self.vertex_buffer.slice(..));
        render_pass.set_vertex_buffer(1, self.instance_buffer.slice(..));
        render_pass.set_index_buffer(self.index_buffer.slice(..), wgpu::IndexFormat::Uint16);
        render_pass.draw_indexed(0..self.num_indices, 0, 0..self.num_instances);
    }
}
