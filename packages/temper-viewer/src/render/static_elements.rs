use temper_viewer_core::types::Point;
use temper_viewer_core::color::{BOARD_BACKGROUND, GRID_DOT, RULER_TICK};
use wgpu::{Device, RenderPass};
use wgpu::util::DeviceExt;

pub struct BoardBackgroundRenderer {
    pipeline: wgpu::RenderPipeline,
    vertex_buffer: wgpu::Buffer,
    num_vertices: u32,
}

impl BoardBackgroundRenderer {
    pub fn new(
        device: &Device,
        shader: &wgpu::ShaderModule,
        camera_layout: &wgpu::BindGroupLayout,
        format: wgpu::TextureFormat,
        board_width: f32,
        board_height: f32,
    ) -> Self {
        let half_w = board_width / 2.0;
        let half_h = board_height / 2.0;
        let color = BOARD_BACKGROUND.to_f32_array();
        let vertices: &[f32] = &[
            0.0,  0.0,   color[0], color[1], color[2], 1.0,
            board_width, 0.0,   color[0], color[1], color[2], 1.0,
            board_width, board_height, color[0], color[1], color[2], 1.0,
            0.0,  0.0,   color[0], color[1], color[2], 1.0,
            board_width, board_height, color[0], color[1], color[2], 1.0,
            0.0,  board_height, color[0], color[1], color[2], 1.0,
        ];
        let vertex_buffer = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some("board_bg_vertex"),
            contents: bytemuck::cast_slice(vertices),
            usage: wgpu::BufferUsages::VERTEX,
        });

        let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: Some("board_bg_layout"),
            bind_group_layouts: &[camera_layout],
            push_constant_ranges: &[],
        });

        let pipeline = device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
            label: Some("board_bg_pipeline"),
            layout: Some(&pipeline_layout),
            vertex: wgpu::VertexState {
                module: shader,
                entry_point: Some("vs_main"),
                buffers: &[wgpu::VertexBufferLayout {
                    array_stride: (6 * std::mem::size_of::<f32>()) as u64,
                    step_mode: wgpu::VertexStepMode::Vertex,
                    attributes: &[
                        wgpu::VertexAttribute {
                            offset: 0,
                            format: wgpu::VertexFormat::Float32x2,
                            shader_location: 0,
                        },
                        wgpu::VertexAttribute {
                            offset: 2 * std::mem::size_of::<f32>() as u64,
                            format: wgpu::VertexFormat::Float32x4,
                            shader_location: 1,
                        },
                    ],
                }],
                compilation_options: Default::default(),
            },
            fragment: Some(wgpu::FragmentState {
                module: shader,
                entry_point: Some("fs_main"),
                targets: &[Some(wgpu::ColorTargetState {
                    format,
                    blend: None,
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
            depth_stencil: None,
            multisample: wgpu::MultisampleState::default(),
            multiview: None,
            cache: None,
        });

        Self { pipeline, vertex_buffer, num_vertices: 6 }
    }

    pub fn draw<'a>(&'a self, render_pass: &mut RenderPass<'a>, camera_bind_group: &'a wgpu::BindGroup) {
        render_pass.set_pipeline(&self.pipeline);
        render_pass.set_bind_group(0, camera_bind_group, &[]);
        render_pass.set_vertex_buffer(0, self.vertex_buffer.slice(..));
        render_pass.draw(0..self.num_vertices, 0..1);
    }
}

pub struct GridRenderer {
    pipeline: wgpu::RenderPipeline,
    vertex_buffer: wgpu::Buffer,
    num_vertices: u32,
}

impl GridRenderer {
    pub fn new(
        device: &Device,
        shader: &wgpu::ShaderModule,
        camera_layout: &wgpu::BindGroupLayout,
        format: wgpu::TextureFormat,
        board_width: f32,
        board_height: f32,
        spacing: f32,
    ) -> Self {
        let mut vertices: Vec<f32> = Vec::new();
        let point_size = 0.3f32;
        let color = GRID_DOT.to_f32_array();
        let mut y = 0.0f32;
        while y <= board_height {
            let mut x = 0.0f32;
            while x <= board_width {
                vertices.extend_from_slice(&[x, y, color[0], color[1], color[2], 1.0, point_size]);
                x += spacing;
            }
            y += spacing;
        }
        let num_vertices = (vertices.len() / 7) as u32;

        let vertex_buffer = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some("grid_vertex"),
            contents: bytemuck::cast_slice(&vertices),
            usage: wgpu::BufferUsages::VERTEX,
        });

        let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: Some("grid_layout"),
            bind_group_layouts: &[camera_layout],
            push_constant_ranges: &[],
        });

        let pipeline = device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
            label: Some("grid_pipeline"),
            layout: Some(&pipeline_layout),
            vertex: wgpu::VertexState {
                module: shader,
                entry_point: Some("vs_main_point"),
                buffers: &[wgpu::VertexBufferLayout {
                    array_stride: (7 * std::mem::size_of::<f32>()) as u64,
                    step_mode: wgpu::VertexStepMode::Vertex,
                    attributes: &[
                        wgpu::VertexAttribute { offset: 0, format: wgpu::VertexFormat::Float32x2, shader_location: 0 },
                        wgpu::VertexAttribute { offset: 8, format: wgpu::VertexFormat::Float32x4, shader_location: 1 },
                        wgpu::VertexAttribute { offset: 24, format: wgpu::VertexFormat::Float32, shader_location: 2 },
                    ],
                }],
                compilation_options: Default::default(),
            },
            fragment: Some(wgpu::FragmentState {
                module: shader,
                entry_point: Some("fs_main"),
                targets: &[Some(wgpu::ColorTargetState {
                    format,
                    blend: Some(wgpu::BlendState::ALPHA_BLENDING),
                    write_mask: wgpu::ColorWrites::ALL,
                })],
                compilation_options: Default::default(),
            }),
            primitive: wgpu::PrimitiveState {
                topology: wgpu::PrimitiveTopology::PointList,
                strip_index_format: None,
                front_face: wgpu::FrontFace::Ccw,
                cull_mode: None,
                polygon_mode: wgpu::PolygonMode::Fill,
                unclipped_depth: false,
                conservative: false,
            },
            depth_stencil: None,
            multisample: wgpu::MultisampleState::default(),
            multiview: None,
            cache: None,
        });

        Self { pipeline, vertex_buffer, num_vertices }
    }

    pub fn draw<'a>(&'a self, render_pass: &mut RenderPass<'a>, camera_bind_group: &'a wgpu::BindGroup) {
        if self.num_vertices == 0 { return; }
        render_pass.set_pipeline(&self.pipeline);
        render_pass.set_bind_group(0, camera_bind_group, &[]);
        render_pass.set_vertex_buffer(0, self.vertex_buffer.slice(..));
        render_pass.draw(0..self.num_vertices, 0..1);
    }
}

pub struct RulerRenderer {
    pipeline: wgpu::RenderPipeline,
    vertex_buffer: wgpu::Buffer,
    num_vertices: u32,
}

impl RulerRenderer {
    pub fn new(
        device: &Device,
        shader: &wgpu::ShaderModule,
        camera_layout: &wgpu::BindGroupLayout,
        format: wgpu::TextureFormat,
        board_width: f32,
        board_height: f32,
        major_interval: f32,
        minor_interval: f32,
    ) -> Self {
        let mut vertices: Vec<f32> = Vec::new();
        let color = RULER_TICK.to_f32_array();
        let ruler_offset = -3.0f32;
        let major_tick_len = 3.0f32;
        let minor_tick_len = 1.5f32;

        let steps_x = (board_width / minor_interval) as usize;
        for i in 0..=steps_x {
            let x = i as f32 * minor_interval;
            let is_major = (x / major_interval).fract().abs() < 0.001;
            let tick_len = if is_major { major_tick_len } else { minor_tick_len };
            let y0 = ruler_offset;
            let y1 = y0 - tick_len;
            vertices.extend_from_slice(&[x, y0, color[0], color[1], color[2], 1.0]);
            vertices.extend_from_slice(&[x, y1, color[0], color[1], color[2], 1.0]);
        }

        let steps_y = (board_height / minor_interval) as usize;
        for i in 0..=steps_y {
            let y = i as f32 * minor_interval;
            let is_major = (y / major_interval).fract().abs() < 0.001;
            let tick_len = if is_major { major_tick_len } else { minor_tick_len };
            let x0 = ruler_offset;
            let x1 = x0 - tick_len;
            vertices.extend_from_slice(&[x0, y, color[0], color[1], color[2], 1.0]);
            vertices.extend_from_slice(&[x1, y, color[0], color[1], color[2], 1.0]);
        }

        let num_vertices = (vertices.len() / 6) as u32;

        let vertex_buffer = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some("ruler_vertex"),
            contents: bytemuck::cast_slice(&vertices),
            usage: wgpu::BufferUsages::VERTEX,
        });

        let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: Some("ruler_layout"),
            bind_group_layouts: &[camera_layout],
            push_constant_ranges: &[],
        });

        let pipeline = device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
            label: Some("ruler_pipeline"),
            layout: Some(&pipeline_layout),
            vertex: wgpu::VertexState {
                module: shader,
                entry_point: Some("vs_main"),
                buffers: &[wgpu::VertexBufferLayout {
                    array_stride: (6 * std::mem::size_of::<f32>()) as u64,
                    step_mode: wgpu::VertexStepMode::Vertex,
                    attributes: &[
                        wgpu::VertexAttribute { offset: 0, format: wgpu::VertexFormat::Float32x2, shader_location: 0 },
                        wgpu::VertexAttribute { offset: 8, format: wgpu::VertexFormat::Float32x4, shader_location: 1 },
                    ],
                }],
                compilation_options: Default::default(),
            },
            fragment: Some(wgpu::FragmentState {
                module: shader,
                entry_point: Some("fs_main"),
                targets: &[Some(wgpu::ColorTargetState {
                    format,
                    blend: None,
                    write_mask: wgpu::ColorWrites::ALL,
                })],
                compilation_options: Default::default(),
            }),
            primitive: wgpu::PrimitiveState {
                topology: wgpu::PrimitiveTopology::LineList,
                strip_index_format: None,
                front_face: wgpu::FrontFace::Ccw,
                cull_mode: None,
                polygon_mode: wgpu::PolygonMode::Fill,
                unclipped_depth: false,
                conservative: false,
            },
            depth_stencil: None,
            multisample: wgpu::MultisampleState::default(),
            multiview: None,
            cache: None,
        });

        Self { pipeline, vertex_buffer, num_vertices }
    }

    pub fn draw<'a>(&'a self, render_pass: &mut RenderPass<'a>, camera_bind_group: &'a wgpu::BindGroup) {
        render_pass.set_pipeline(&self.pipeline);
        render_pass.set_bind_group(0, camera_bind_group, &[]);
        render_pass.set_vertex_buffer(0, self.vertex_buffer.slice(..));
        render_pass.draw(0..self.num_vertices, 0..1);
    }
}
