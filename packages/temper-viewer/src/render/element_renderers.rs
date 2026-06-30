use temper_viewer_core::model::{Trace, Zone, Pad};
use temper_viewer_core::color;
use temper_viewer_core::types::Point;
use wgpu::{Device, Queue, RenderPass};
use wgpu::util::DeviceExt;

pub struct TraceRenderer {
    primitives: Vec<LayerLines>,
    visible: bool,
}

struct LayerLines {
    pipeline: wgpu::RenderPipeline,
    vertex_buffer: wgpu::Buffer,
    num_vertices: u32,
}

impl TraceRenderer {
    pub fn new() -> Self {
        Self { primitives: Vec::new(), visible: true }
    }

    pub fn update(
        &mut self,
        device: &Device,
        shader: &wgpu::ShaderModule,
        camera_layout: &wgpu::BindGroupLayout,
        format: wgpu::TextureFormat,
        traces: &[Trace],
    ) {
        self.primitives.clear();

        let mut by_layer: std::collections::BTreeMap<String, Vec<f32>> = std::collections::BTreeMap::new();
        for t in traces {
            let color_arr = color::layer_color(&t.layer).to_f32_array();
            let entry = by_layer.entry(t.layer.clone()).or_default();
            entry.extend_from_slice(&[
                t.start.x, t.start.y, color_arr[0], color_arr[1], color_arr[2], 1.0,
                t.end.x, t.end.y, color_arr[0], color_arr[1], color_arr[2], 1.0,
            ]);
        }

        for (layer, vertices) in &by_layer {
            let vertex_buffer = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
                label: Some(&format!("trace_{}", layer)),
                contents: bytemuck::cast_slice(vertices),
                usage: wgpu::BufferUsages::VERTEX,
            });

            let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
                label: None,
                bind_group_layouts: &[camera_layout],
                push_constant_ranges: &[],
            });

            let pipeline = device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
                label: None,
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
                        blend: Some(wgpu::BlendState::ALPHA_BLENDING),
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
                multisample: wgpu::MultisampleState::default(),
                multiview: None,
                cache: None,
                depth_stencil: None,
            });

            let num_vertices = (vertices.len() / 6) as u32;
            self.primitives.push(LayerLines { pipeline, vertex_buffer, num_vertices });
        }
    }

    pub fn set_visible(&mut self, visible: bool) { self.visible = visible; }

    pub fn draw<'a>(
        &'a self, render_pass: &mut RenderPass<'a>,
        camera_bind_group: &'a wgpu::BindGroup,
    ) {
        if !self.visible { return; }
        for layer_lines in &self.primitives {
            if layer_lines.num_vertices == 0 { continue; }
            render_pass.set_pipeline(&layer_lines.pipeline);
            render_pass.set_bind_group(0, camera_bind_group, &[]);
            render_pass.set_vertex_buffer(0, layer_lines.vertex_buffer.slice(..));
            render_pass.draw(0..layer_lines.num_vertices, 0..1);
        }
    }
}

pub struct ZoneRenderer {
    pipeline: wgpu::RenderPipeline,
    vertex_buffer: wgpu::Buffer,
    num_vertices: u32,
    visible: bool,
}

impl ZoneRenderer {
    pub fn new(
        device: &Device, shader: &wgpu::ShaderModule,
        camera_layout: &wgpu::BindGroupLayout, format: wgpu::TextureFormat,
    ) -> Self {
        let vertex_buffer = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("zone_vertex"),
            size: 1024,
            usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });

        let layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: None,
            bind_group_layouts: &[camera_layout],
            push_constant_ranges: &[],
        });

        let pipeline = device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
            label: Some("zone_pipeline"),
            layout: Some(&layout),
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

        Self { pipeline, vertex_buffer, num_vertices: 0, visible: true }
    }

    pub fn update(&mut self, device: &Device, queue: &Queue, zones: &[Zone]) {
        let mut vertices: Vec<f32> = Vec::new();
        for zone in zones {
            if zone.polygon.len() < 3 { continue; }
            let fill_color = zone.color.as_deref()
                .and_then(hex_to_rgb)
                .map(|c| [c[0], c[1], c[2], 0.2f32])
                .unwrap_or([0.5, 0.5, 0.5, 0.2]);

            let pts = &zone.polygon;
            for i in 1..pts.len().saturating_sub(1) {
                vertices.extend_from_slice(&[
                    pts[0].x, pts[0].y, fill_color[0], fill_color[1], fill_color[2], fill_color[3],
                    pts[i].x, pts[i].y, fill_color[0], fill_color[1], fill_color[2], fill_color[3],
                    pts[i+1].x, pts[i+1].y, fill_color[0], fill_color[1], fill_color[2], fill_color[3],
                ]);
            }
        }
        self.num_vertices = (vertices.len() / 6) as u32;
        if self.num_vertices > 0 {
            let needed = (vertices.len() * std::mem::size_of::<f32>()) as u64;
            if needed > self.vertex_buffer.size() {
                self.vertex_buffer = device.create_buffer(&wgpu::BufferDescriptor {
                    label: Some("zone_vertex_resized"),
                    size: needed,
                    usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
                    mapped_at_creation: false,
                });
            }
            queue.write_buffer(&self.vertex_buffer, 0, bytemuck::cast_slice(&vertices));
        }
    }

    pub fn set_visible(&mut self, visible: bool) { self.visible = visible; }

    pub fn draw<'a>(&'a self, render_pass: &mut RenderPass<'a>, camera_bind_group: &'a wgpu::BindGroup) {
        if !self.visible || self.num_vertices == 0 { return; }
        render_pass.set_pipeline(&self.pipeline);
        render_pass.set_bind_group(0, camera_bind_group, &[]);
        render_pass.set_vertex_buffer(0, self.vertex_buffer.slice(..));
        render_pass.draw(0..self.num_vertices, 0..1);
    }
}

pub struct RatsnestRenderer {
    pipeline: wgpu::RenderPipeline,
    vertex_buffer: wgpu::Buffer,
    num_vertices: u32,
    visible: bool,
}

impl RatsnestRenderer {
    pub fn new(
        device: &Device, shader: &wgpu::ShaderModule,
        camera_layout: &wgpu::BindGroupLayout, format: wgpu::TextureFormat,
    ) -> Self {
        let vertex_buffer = device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("ratsnest_vertex"),
            size: 1024,
            usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });

        let layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: None,
            bind_group_layouts: &[camera_layout],
            push_constant_ranges: &[],
        });

        let pipeline = device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
            label: Some("ratsnest_pipeline"),
            layout: Some(&layout),
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
                    blend: Some(wgpu::BlendState::ALPHA_BLENDING),
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
            multisample: wgpu::MultisampleState::default(),
            multiview: None,
            cache: None,
            depth_stencil: None,
        });

        Self { pipeline, vertex_buffer, num_vertices: 0, visible: false }
    }

    pub fn update(&mut self, device: &Device, queue: &Queue, pads: &[Pad]) {
        let color = color::RATSNEST_LINE.to_f32_array();
        let c = [color[0], color[1], color[2], 0.3f32];
        let mut vertices: Vec<f32> = Vec::new();

        let mut net_pads: std::collections::BTreeMap<String, Vec<(f32, f32)>> = std::collections::BTreeMap::new();
        for pad in pads {
            if let Some(ref net) = pad.net {
                if !net.is_empty() {
                    net_pads.entry(net.clone()).or_default().push((pad.position.x, pad.position.y));
                }
            }
        }

        for positions in net_pads.values() {
            for i in 0..positions.len() {
                for j in (i + 1)..positions.len() {
                    vertices.extend_from_slice(&[
                        positions[i].0, positions[i].1, c[0], c[1], c[2], c[3],
                        positions[j].0, positions[j].1, c[0], c[1], c[2], c[3],
                    ]);
                }
            }
        }

        self.num_vertices = (vertices.len() / 6) as u32;
        if self.num_vertices > 0 {
            let needed = (vertices.len() * std::mem::size_of::<f32>()) as u64;
            if needed > self.vertex_buffer.size() {
                self.vertex_buffer = device.create_buffer(&wgpu::BufferDescriptor {
                    label: Some("ratsnest_resized"),
                    size: needed,
                    usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
                    mapped_at_creation: false,
                });
            }
            queue.write_buffer(&self.vertex_buffer, 0, bytemuck::cast_slice(&vertices));
        }
    }

    pub fn set_visible(&mut self, visible: bool) { self.visible = visible; }

    pub fn draw<'a>(&'a self, render_pass: &mut RenderPass<'a>, camera_bind_group: &'a wgpu::BindGroup) {
        if !self.visible || self.num_vertices == 0 { return; }
        render_pass.set_pipeline(&self.pipeline);
        render_pass.set_bind_group(0, camera_bind_group, &[]);
        render_pass.set_vertex_buffer(0, self.vertex_buffer.slice(..));
        render_pass.draw(0..self.num_vertices, 0..1);
    }
}

fn hex_to_rgb(hex: &str) -> Option<[f32; 3]> {
    let hex = hex.trim_start_matches('#');
    if hex.len() != 6 { return None; }
    let r = u8::from_str_radix(&hex[0..2], 16).ok()?;
    let g = u8::from_str_radix(&hex[2..4], 16).ok()?;
    let b = u8::from_str_radix(&hex[4..6], 16).ok()?;
    Some([r as f32 / 255.0, g as f32 / 255.0, b as f32 / 255.0])
}
