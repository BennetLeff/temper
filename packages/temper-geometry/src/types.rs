use std::f64;

/// A 2D point.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Point {
    pub x: f64,
    pub y: f64,
}

impl Point {
    pub const fn new(x: f64, y: f64) -> Self {
        Self { x, y }
    }

    pub const fn zero() -> Self {
        Self { x: 0.0, y: 0.0 }
    }

    pub fn distance(&self, other: &Point) -> f64 {
        let dx = self.x - other.x;
        let dy = self.y - other.y;
        (dx * dx + dy * dy).sqrt()
    }

    pub fn distance_squared(&self, other: &Point) -> f64 {
        let dx = self.x - other.x;
        let dy = self.y - other.y;
        dx * dx + dy * dy
    }

    pub fn midpoint(&self, other: &Point) -> Point {
        Point {
            x: (self.x + other.x) * 0.5,
            y: (self.y + other.y) * 0.5,
        }
    }
}

impl std::ops::Add for Point {
    type Output = Point;
    fn add(self, rhs: Point) -> Point {
        Point::new(self.x + rhs.x, self.y + rhs.y)
    }
}

impl std::ops::Sub for Point {
    type Output = Point;
    fn sub(self, rhs: Point) -> Point {
        Point::new(self.x - rhs.x, self.y - rhs.y)
    }
}

impl std::ops::Mul<f64> for Point {
    type Output = Point;
    fn mul(self, rhs: f64) -> Point {
        Point::new(self.x * rhs, self.y * rhs)
    }
}

/// A 2D vector (direction and magnitude).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Vec2 {
    pub x: f64,
    pub y: f64,
}

impl Vec2 {
    pub const fn new(x: f64, y: f64) -> Self {
        Self { x, y }
    }

    pub fn dot(&self, other: &Vec2) -> f64 {
        self.x * other.x + self.y * other.y
    }

    pub fn cross(&self, other: &Vec2) -> f64 {
        self.x * other.y - self.y * other.x
    }

    pub fn length(&self) -> f64 {
        (self.x * self.x + self.y * self.y).sqrt()
    }

    pub fn length_squared(&self) -> f64 {
        self.x * self.x + self.y * self.y
    }

    pub fn normalize(&self) -> Vec2 {
        let len = self.length();
        if len > 1e-15 {
            Vec2 {
                x: self.x / len,
                y: self.y / len,
            }
        } else {
            Vec2 { x: 0.0, y: 0.0 }
        }
    }
}

impl From<Point> for Vec2 {
    fn from(p: Point) -> Self {
        Vec2 { x: p.x, y: p.y }
    }
}

/// An axis-aligned rectangle defined by (x, y) and (width, height).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Rect {
    pub x: f64,
    pub y: f64,
    pub w: f64,
    pub h: f64,
}

impl Rect {
    pub const fn new(x: f64, y: f64, w: f64, h: f64) -> Self {
        Self { x, y, w, h }
    }

    pub fn from_center(cx: f64, cy: f64, half_w: f64, half_h: f64) -> Self {
        Self {
            x: cx - half_w,
            y: cy - half_h,
            w: half_w * 2.0,
            h: half_h * 2.0,
        }
    }

    pub fn center(&self) -> Point {
        Point::new(self.x + self.w * 0.5, self.y + self.h * 0.5)
    }

    pub fn area(&self) -> f64 {
        self.w * self.h
    }

    pub fn contains_point(&self, p: &Point) -> bool {
        p.x >= self.x
            && p.x <= self.x + self.w
            && p.y >= self.y
            && p.y <= self.y + self.h
    }

    pub fn corners(&self) -> [Point; 4] {
        [
            Point::new(self.x, self.y),
            Point::new(self.x + self.w, self.y),
            Point::new(self.x + self.w, self.y + self.h),
            Point::new(self.x, self.y + self.h),
        ]
    }

    pub fn dimensions(&self) -> (f64, f64) {
        (self.w, self.h)
    }
}

/// An axis-aligned bounding box defined by (x_min, y_min) and (x_max, y_max).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct AABB {
    pub x_min: f64,
    pub y_min: f64,
    pub x_max: f64,
    pub y_max: f64,
}

impl AABB {
    pub const fn new(x_min: f64, y_min: f64, x_max: f64, y_max: f64) -> Self {
        Self {
            x_min,
            y_min,
            x_max,
            y_max,
        }
    }

    pub fn from_points(points: &[Point]) -> Self {
        let mut min_x = f64::INFINITY;
        let mut min_y = f64::INFINITY;
        let mut max_x = f64::NEG_INFINITY;
        let mut max_y = f64::NEG_INFINITY;
        for p in points {
            if p.x < min_x {
                min_x = p.x;
            }
            if p.y < min_y {
                min_y = p.y;
            }
            if p.x > max_x {
                max_x = p.x;
            }
            if p.y > max_y {
                max_y = p.y;
            }
        }
        Self {
            x_min: min_x,
            y_min: min_y,
            x_max: max_x,
            y_max: max_y,
        }
    }

    pub fn width(&self) -> f64 {
        self.x_max - self.x_min
    }

    pub fn height(&self) -> f64 {
        self.y_max - self.y_min
    }

    pub fn center(&self) -> Point {
        Point::new(
            (self.x_min + self.x_max) * 0.5,
            (self.y_min + self.y_max) * 0.5,
        )
    }

    pub fn area(&self) -> f64 {
        self.width() * self.height()
    }

    pub fn intersects(&self, other: &AABB) -> bool {
        self.x_min <= other.x_max
            && self.x_max >= other.x_min
            && self.y_min <= other.y_max
            && self.y_max >= other.y_min
    }

    pub fn overlap_area(&self, other: &AABB) -> f64 {
        if !self.intersects(other) {
            return 0.0;
        }
        let dx = self.x_max.min(other.x_max) - self.x_min.max(other.x_min);
        let dy = self.y_max.min(other.y_max) - self.y_min.max(other.y_min);
        dx * dy
    }

    pub fn union(&self, other: &AABB) -> AABB {
        AABB {
            x_min: self.x_min.min(other.x_min),
            y_min: self.y_min.min(other.y_min),
            x_max: self.x_max.max(other.x_max),
            y_max: self.y_max.max(other.y_max),
        }
    }

    pub fn expand(&self, margin: f64) -> AABB {
        AABB {
            x_min: self.x_min - margin,
            y_min: self.y_min - margin,
            x_max: self.x_max + margin,
            y_max: self.y_max + margin,
        }
    }

    pub fn contains_point(&self, p: &Point) -> bool {
        p.x >= self.x_min && p.x <= self.x_max && p.y >= self.y_min && p.y <= self.y_max
    }
}

impl From<Rect> for AABB {
    fn from(r: Rect) -> Self {
        AABB {
            x_min: r.x,
            y_min: r.y,
            x_max: r.x + r.w,
            y_max: r.y + r.h,
        }
    }
}

/// A line segment between two points.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Segment {
    pub start: Point,
    pub end: Point,
}

impl Segment {
    pub fn new(start: Point, end: Point) -> Self {
        Self { start, end }
    }

    pub fn length(&self) -> f64 {
        self.start.distance(&self.end)
    }

    pub fn midpoint(&self) -> Point {
        self.start.midpoint(&self.end)
    }

    pub fn angle(&self) -> f64 {
        let dx = self.end.x - self.start.x;
        let dy = self.end.y - self.start.y;
        dy.atan2(dx)
    }

    pub fn nearest_point(&self, p: &Point) -> Point {
        let dx = self.end.x - self.start.x;
        let dy = self.end.y - self.start.y;
        let len_sq = dx * dx + dy * dy;
        if len_sq < 1e-15 {
            return self.start;
        }
        let t = ((p.x - self.start.x) * dx + (p.y - self.start.y) * dy) / len_sq;
        let t_clamped = t.clamp(0.0, 1.0);
        Point::new(
            self.start.x + t_clamped * dx,
            self.start.y + t_clamped * dy,
        )
    }
}

/// A polygon defined by an ordered list of vertices.
#[derive(Debug, Clone, PartialEq)]
pub struct Polygon {
    pub vertices: Vec<Point>,
}

impl Polygon {
    pub fn new(vertices: Vec<Point>) -> Self {
        Self { vertices }
    }

    pub fn signed_area(&self) -> f64 {
        let n = self.vertices.len();
        if n < 3 {
            return 0.0;
        }
        let mut area = 0.0;
        for i in 0..n {
            let j = (i + 1) % n;
            area += self.vertices[i].x * self.vertices[j].y;
            area -= self.vertices[j].x * self.vertices[i].y;
        }
        area * 0.5
    }

    pub fn area(&self) -> f64 {
        self.signed_area().abs()
    }

    pub fn centroid(&self) -> Point {
        let n = self.vertices.len();
        if n == 0 {
            return Point::zero();
        }
        let mut cx = 0.0;
        let mut cy = 0.0;
        for p in &self.vertices {
            cx += p.x;
            cy += p.y;
        }
        Point::new(cx / n as f64, cy / n as f64)
    }

    pub fn perimeter(&self) -> f64 {
        let n = self.vertices.len();
        if n < 2 {
            return 0.0;
        }
        let mut perim = 0.0;
        for i in 0..n {
            let j = (i + 1) % n;
            perim += self.vertices[i].distance(&self.vertices[j]);
        }
        perim
    }

    pub fn bounding_box(&self) -> AABB {
        AABB::from_points(&self.vertices)
    }

    pub fn contains_point(&self, p: &Point) -> bool {
        let n = self.vertices.len();
        if n < 3 {
            return false;
        }
        let mut inside = false;
        let mut j = n - 1;
        for i in 0..n {
            let vi = &self.vertices[i];
            let vj = &self.vertices[j];
            if (vi.y > p.y) != (vj.y > p.y) {
                let x_intersect = vj.x + (p.y - vj.y) / (vi.y - vj.y) * (vi.x - vj.x);
                if p.x < x_intersect {
                    inside = !inside;
                }
            }
            j = i;
        }
        inside
    }

    pub fn nearest_point(&self, p: &Point) -> Point {
        let n = self.vertices.len();
        if n < 2 {
            return self.vertices.first().copied().unwrap_or(*p);
        }
        let mut best_dist = f64::INFINITY;
        let mut best_point = *p;
        for i in 0..n {
            let j = (i + 1) % n;
            let seg = Segment::new(self.vertices[i], self.vertices[j]);
            let np = seg.nearest_point(p);
            let d = np.distance(p);
            if d < best_dist {
                best_dist = d;
                best_point = np;
            }
        }
        best_point
    }

    pub fn translate(&self, dx: f64, dy: f64) -> Polygon {
        Polygon::new(
            self.vertices
                .iter()
                .map(|p| Point::new(p.x + dx, p.y + dy))
                .collect(),
        )
    }

    pub fn scale(&self, sx: f64, sy: f64) -> Polygon {
        Polygon::new(
            self.vertices
                .iter()
                .map(|p| Point::new(p.x * sx, p.y * sy))
                .collect(),
        )
    }
}
