use wgpu::{Device, Queue, SurfaceConfiguration, TextureFormat};

pub struct RenderState {
    pub device: Device,
    pub queue: Queue,
    pub config: SurfaceConfiguration,
    pub format: TextureFormat,
}

impl RenderState {
    #[cfg(target_arch = "wasm32")]
    pub async fn new_from_canvas(canvas: &web_sys::HtmlCanvasElement) -> Result<Self, String> {
        let instance = wgpu::Instance::new(&wgpu::InstanceDescriptor {
            backends: wgpu::Backends::all(),
            ..Default::default()
        });

        let surface = instance
            .create_surface_from_canvas(canvas)
            .map_err(|e| format!("Failed to create surface: {:?}", e))?;

        Self::from_surface(instance, surface, canvas.width(), canvas.height()).await
    }

    #[cfg(not(target_arch = "wasm32"))]
    pub async fn new_from_canvas(_canvas: &web_sys::HtmlCanvasElement) -> Result<Self, String> {
        Err("WASM renderer requires wasm32 target".to_string())
    }

    pub async fn from_surface(
        instance: wgpu::Instance,
        surface: wgpu::Surface<'_>,
        width: u32,
        height: u32,
    ) -> Result<Self, String> {
        let adapter = instance
            .request_adapter(&wgpu::RequestAdapterOptions {
                power_preference: wgpu::PowerPreference::HighPerformance,
                compatible_surface: Some(&surface),
                force_fallback_adapter: false,
            })
            .await
            .ok_or("No suitable GPU adapter found")?;

        let (device, queue) = adapter
            .request_device(
                &wgpu::DeviceDescriptor {
                    required_features: wgpu::Features::empty(),
                    required_limits: wgpu::Limits::downlevel_webgl2_defaults(),
                    ..Default::default()
                },
                None,
            )
            .await
            .map_err(|e| format!("Failed to create device: {:?}", e))?;

        let caps = surface.get_capabilities(&adapter);
        let format = caps
            .formats
            .iter()
            .copied()
            .find(TextureFormat::is_srgb)
            .unwrap_or(caps.formats[0]);

        let config = wgpu::SurfaceConfiguration {
            usage: wgpu::TextureUsages::RENDER_ATTACHMENT,
            format,
            width,
            height,
            present_mode: wgpu::PresentMode::AutoVsync,
            alpha_mode: caps.alpha_modes[0],
            view_formats: vec![],
            desired_maximum_frame_latency: 2,
        };
        surface.configure(&device, &config);

        Ok(Self { device, queue, config, format })
    }

    pub fn resize(&mut self, surface: &wgpu::Surface<'_>, width: u32, height: u32) {
        if width > 0 && height > 0 {
            self.config.width = width;
            self.config.height = height;
            surface.configure(&self.device, &self.config);
        }
    }
}
