---
date: 2026-07-01
status: active
source: docs/plans/2026-07-01-003-feat-ccap-alternating-projections-plan.md
category: algorithm
---

# C-CAP Mathematical Basis

## 1. Dykstra's Alternating Projections

C-CAP uses Boyle & Dykstra's algorithm (1986) for projecting onto the
intersection of closed convex sets.

### Statement

Let $C_1, C_2, \ldots, C_k \subseteq \mathbb{R}^2$ be closed convex sets with
non-empty intersection $\bigcap C_i \neq \emptyset$. Dykstra's algorithm
iterates:

$$
\begin{aligned}
p_t^{(i)} &= x_{t-1} + r_t^{(i)} \quad &\text{(apply correction)} \\
x_t^{(i)} &= P_{C_i}(p_t^{(i)}) \quad &\text{(project onto constraint set)} \\
r_{t+1}^{(i)} &= p_t^{(i)} - x_t^{(i)} \quad &\text{(store correction)}
\end{aligned}
$$

where $P_{C_i}$ is the orthogonal projection onto $C_i$, and correction
vectors $r_t^{(i)}$ are stored in a sparse dict keyed by
`(component_ref, constraint_id)`.

### Convergence

For closed convex sets, Dykstra's iterates converge to a point in $\bigcap C_i$.
The correction vectors ensure that prior constraint satisfaction is not undone
by subsequent projections. The residual $r_t^{(i)} \to 0$ as $t \to \infty$.

### Component ordering heuristic

Components are processed in descending order of constraint count ($K_c$),
so the most-constrained components stabilize first. The total work per cycle
is $O(\sum_c K_c)$ projection evaluations.

---

## 2. Feasibility Pump Relaxation

Pairwise constraints (clearance, spacing, group separation) define a set
$\{ (p_i, p_j) : \|p_i - p_j\| \geq d_{ij} \}$. Hard projection of this set
is NP-hard (disk packing; Demaine, Fekete & Lang, 2005).

Instead, C-CAP defines a violation function:

$$
L(p) = \frac{1}{2} \sum_{(i,j,d) \in \mathcal{P}} \max(0, d - \|p_i - p_j\|)^2
$$

with gradient:

$$
\frac{\partial L}{\partial p_i} = \sum_{j: (i,j,d) \in \mathcal{P}}
(p_i - p_j) \cdot
\frac{\max(0, d - \|p_i - p_j\|)}{\max(\|p_i - p_j\|, \varepsilon)}
$$

where $\varepsilon = 10^{-6}$ prevents NaN when components share a position.

### Priority tiers

1. **Safety-critical** (step = 0.5mm): HV/LV clearance, noise isolation
2. **Quality** (step = 0.2mm): component spacing, group separation, thermal spread

Each tier iterates until its violation sum changes by less than 1% over 3
iterations. Proximity-within-groups is deferred to the optimizer.

### Post-pump re-projection

After each pump step, one Dykstra cycle is re-run to re-establish unary
feasibility. This prevents the pump gradient from pushing components outside
zones or into keepouts.

---

## 3. Projection Operators

### Point-to-half-plane

For a half-plane $\{ p : a \cdot p \geq c \}$:

$$
P_H(p) = p + \max(0, c - a \cdot p) \cdot \frac{a}{\|a\|^2}
$$

In the horizontal axis-aligned case ($a = (0, 1)$, $c$ = boundary):

$$P_H(p) = (p_x, \max(p_y, c)) \quad \text{(HV, above boundary)}$$

### Point-to-polygon

For zone containment: use winding-number test for interior detection. If
outside, project to nearest boundary point:

$$
P_Z(p) = \begin{cases}
p & \text{if } \text{winding}(p, Z) \neq 0 \\
\text{argmin}_{q \in \partial Z} \|p - q\| & \text{otherwise}
\end{cases}
$$

### Point-to-line-segment

For segment $\overline{ab}$, the orthogonal projection parameter is:

$$
t = \text{clamp}\!\left(\frac{\langle p - a, b - a \rangle}{\|b - a\|^2}, 0, 1\right)
$$

Result: $P(p) = a + t(b - a)$. Degenerate segments ($\|b-a\| \to 0$) return
$a$ via denominator clipping.

### Point-to-board (rectangular clamp)

For the axis-aligned board rect $[m_x, W - m_x] \times [m_y, H - m_y]$:

$$P_B(p) = (\text{clamp}(p_x, m_x, W - m_x), \text{clamp}(p_y, m_y, H - m_y))$$

### Keepout avoidance

For keepout rect $R = [k_x^-, k_x^+] \times [k_y^-, k_y^+]$, the feasible
region is the complement of $R$ expanded by component half-size. Projection:
find the nearest point on the boundary of the expanded rect.

---

## 4. Oscillation Detection

Dykstra can oscillate when constraint sets are incompatible (e.g., overlapping
zone and keepout). C-CAP detects 2-cycle oscillation:

A component oscillates if, for 2 consecutive 2-step windows:

$$\|p_t - p_{t-2}\| < \tau \quad \text{AND} \quad \|p_t - p_{t-1}\| > 10\tau$$

where $\tau = \texttt{ccap\_convergence\_tol}$ (default 0.01mm). The first
condition detects return-to-prior-state; the second excludes slow legitimate
drift. On detection, the component is flagged as unresolved with best-effort
position retained.

---

## References

- Boyle, J. P., & Dykstra, R. L. (1986). A method for finding projections
  onto the intersection of convex sets in Hilbert spaces.
- von Neumann, J. (1950). Functional Operators, Vol. II. Princeton University
  Press.
- Fischetti, M., Glover, F., & Lodi, A. (2005). The feasibility pump.
  Mathematical Programming, 104(1).
- Demaine, E. D., Fekete, S. P., & Lang, R. J. (2005). Circle packing is
  NP-hard.
