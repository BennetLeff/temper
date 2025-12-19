"""
FreeRouting autorouter integration for temper-placer.

This module provides a Python wrapper for the FreeRouting autorouter (Java).
It handles the conversion from KiCad to Specctra DSN format, execution
of FreeRouting, and importing the resulting Specctra SES file back into KiCad.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

@dataclass
class RoutingMetrics:
    """Metrics from a routing run."""
    success: bool
    completion_rate: float  # 0.0 to 1.0
    wirelength_mm: float
    via_count: int
    unrouted_count: int
    routing_time_s: float
    error_message: Optional[str] = None

class FreeRoutingWrapper:
    """
    Wrapper for FreeRouting autorouter.
    
    Requires:
    - KiCad installed (for pcbnew python module)
    - Java Runtime Environment (for freerouting.jar)
    - freerouting.jar path
    """
    
    def __init__(
        self,
        jar_path: Path,
        kicad_python_path: Path = Path("/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3"),
        java_path: str = "java",
    ):
        self.jar_path = jar_path
        self.kicad_python_path = kicad_python_path
        self.java_path = java_path
        
        # Verify jar exists
        if not jar_path.exists():
            print(f"Warning: FreeRouting JAR not found at {jar_path}")

    def route_pcb(
        self,
        pcb_path: Path,
        output_pcb: Optional[Path] = None,
        timeout_s: int = 300,
        keep_temp_files: bool = False,
    ) -> Tuple[Optional[Path], RoutingMetrics]:
        """
        Export PCB to DSN, route with FreeRouting, and import SES back.
        
        Returns (output_pcb_path, metrics).
        """
        if output_pcb is None:
            output_pcb = pcb_path.with_name(pcb_path.stem + "_routed" + pcb_path.suffix)
            
        with tempfile.TemporaryDirectory(prefix="freerouting_") as temp_dir:
            temp_path = Path(temp_dir)
            dsn_path = temp_path / "board.dsn"
            ses_path = temp_path / "board.ses"
            
            # 1. Export KiCad to DSN
            if not self._export_dsn(pcb_path, dsn_path):
                return None, RoutingMetrics(False, 0, 0, 0, 0, 0, "DSN Export failed")
            
            # 2. Run FreeRouting
            start_time = os.times().elapsed
            success, error = self._run_freerouting(dsn_path, ses_path, timeout_s)
            end_time = os.times().elapsed
            duration = end_time - start_time
            
            if not success or not ses_path.exists():
                return None, RoutingMetrics(False, 0, 0, 0, 0, duration, f"FreeRouting failed: {error}")
            
            # 3. Import SES to KiCad
            if not self._import_ses(pcb_path, ses_path, output_pcb):
                return None, RoutingMetrics(False, 0, 0, 0, 0, duration, "SES Import failed")
                
            # 4. Parse metrics (placeholder logic - real implementation would parse SES/logs)
            metrics = RoutingMetrics(
                success=True,
                completion_rate=1.0,  # Should parse from SES
                wirelength_mm=0.0,    # Should parse from SES
                via_count=0,          # Should parse from SES
                unrouted_count=0,
                routing_time_s=duration
            )
            
            if keep_temp_files:
                # Copy to original directory for debugging
                import shutil
                shutil.copy(dsn_path, pcb_path.with_suffix(".dsn"))
                if ses_path.exists():
                    shutil.copy(ses_path, pcb_path.with_suffix(".ses"))
            
            return output_pcb, metrics

    def _export_dsn(self, pcb_path: Path, dsn_path: Path) -> bool:
        """Export PCB to Specctra DSN using KiCad python."""
        script_content = f"""
import sys
import pcbnew
import wx
app = wx.App()
board = pcbnew.LoadBoard('{pcb_path}')
result = pcbnew.ExportSpecctraDSN(board, '{dsn_path}')
sys.exit(0 if result else 1)
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py') as f:
            f.write(script_content)
            f.flush()
            try:
                # We need to set PYTHONPATH to include KiCad site-packages
                kicad_site_packages = "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/lib/python3.9/site-packages"
                env = os.environ.copy()
                env["PYTHONPATH"] = kicad_site_packages + os.pathsep + env.get("PYTHONPATH", "")
                
                result = subprocess.run(
                    [str(self.kicad_python_path), f.name],
                    capture_output=True,
                    text=True,
                    env=env
                )
                return result.returncode == 0
            except Exception as e:
                print(f"DSN Export error: {e}")
                return False

    def _import_ses(self, pcb_path: Path, ses_path: Path, output_pcb: Path) -> bool:
        """Import Specctra SES into KiCad using KiCad python."""
        script_content = f"""
import sys
import pcbnew
import wx
app = wx.App()
board = pcbnew.LoadBoard('{pcb_path}')
result = pcbnew.ImportSpecctraSES(board, '{ses_path}')
if result:
    board.Save('{output_pcb}')
sys.exit(0 if result else 1)
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py') as f:
            f.write(script_content)
            f.flush()
            try:
                kicad_site_packages = "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/lib/python3.9/site-packages"
                env = os.environ.copy()
                env["PYTHONPATH"] = kicad_site_packages + os.pathsep + env.get("PYTHONPATH", "")
                
                result = subprocess.run(
                    [str(self.kicad_python_path), f.name],
                    capture_output=True,
                    text=True,
                    env=env
                )
                return result.returncode == 0
            except Exception as e:
                print(f"SES Import error: {e}")
                return False

    def _run_freerouting(self, dsn_path: Path, ses_path: Path, timeout_s: int) -> Tuple[bool, str]:
        """Execute FreeRouting JAR."""
        # Command: java -jar freerouting.jar -de board.dsn -do board.ses -mp 100
        cmd = [
            self.java_path,
            "-jar", str(self.jar_path),
            "-de", str(dsn_path),
            "-do", str(ses_path),
            "-mp", "50",  # Max passes
            "-mt", str(timeout_s)  # Timeout
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s + 10)
            if result.returncode != 0:
                return False, result.stderr
            return True, ""
        except subprocess.TimeoutExpired:
            return False, "FreeRouting timed out"
        except Exception as e:
            return False, str(e)
