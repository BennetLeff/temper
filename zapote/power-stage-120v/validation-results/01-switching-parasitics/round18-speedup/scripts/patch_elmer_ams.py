#!/usr/bin/env python3
"""Round 18: Elmer patch that makes AMS consistent with Elmer's diagonal scaling.

    patch_elmer_ams.py ELMERFEM/fem/src/SParIterSolver.F90 OUT.F90

Why. Elmer's SolveLinearSystem scales the system symmetrically before Hypre
sees it (Linear System Scaling, default True): A^ = S A S, S = diag(s),
s_i = 1/sqrt|a_ii| (SolverUtils.F90 ScaleLinearSystemDiagonal). The discrete
gradient G and the Nedelec interpolation Pi that SParIterSolver.F90 passes to
AMS (PrepareHypreAMS) are built from the mesh and are NOT scaled. AMS assumes
range(G) is the near-kernel of the matrix it is given; for A^ that is
S^-1 range(G), not range(G), and likewise the vector-nodal space is S^-1 Pi.
On a graded mesh (35 um copper layers to 4 mm far-field cells) S varies by
orders of magnitude, so AMS's auxiliary-space corrections act on the wrong
vectors. This patch, when the solver section sets
    AMS Scale Auxiliary = Logical True
divides row i of G and Pi by s_i (= Matrix % DiagScaling(i)) before the AMS
setup. Without the keyword nothing changes (the default path is untouched).
The patched file is compiled into a separate copy of the install
(build_elmer_r18.sh); the live chain's install is never modified.
"""
import sys

src, out = sys.argv[1], sys.argv[2]
s = open(src).read()
anchor = "      CALL PrepareHypreAMS() \n"
assert s.count(anchor) == 1, "anchor not found exactly once"
patch = anchor + """      ! --- round 18 patch: AMS auxiliary spaces consistent with diagonal scaling ---
      IF( ListGetLogical( Params,'AMS Scale Auxiliary',Found ) ) THEN
        IF( ASSOCIATED( Matrix % DiagScaling ) ) THEN
          WRITE(Message,'(A,4I10)') 'R18: scaling G/Pi rows by 1/DiagScaling; rows G, Pi, A, scal: ', &
              GM % NumberOfRows, PiM % NumberOfRows, Matrix % NumberOfRows, SIZE(Matrix % DiagScaling)
          CALL Info(Caller,Message,Level=4)
          DO i=1,MIN(GM % NumberOfRows, SIZE(Matrix % DiagScaling))
            GM % Values(GM % Rows(i):GM % Rows(i+1)-1) = &
                GM % Values(GM % Rows(i):GM % Rows(i+1)-1) / Matrix % DiagScaling(i)
          END DO
          DO i=1,MIN(PiM % NumberOfRows, SIZE(Matrix % DiagScaling))
            PiM % Values(PiM % Rows(i):PiM % Rows(i+1)-1) = &
                PiM % Values(PiM % Rows(i):PiM % Rows(i+1)-1) / Matrix % DiagScaling(i)
          END DO
        ELSE
          CALL Warn(Caller,'R18: AMS Scale Auxiliary set but no DiagScaling vector; G/Pi unscaled')
        END IF
      END IF
      ! --- end round 18 patch ---
"""
s = s.replace(anchor, patch)
open(out, "w").write(s)
print("patched", out)
