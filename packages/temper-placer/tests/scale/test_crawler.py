
from temper_placer.scale.crawler import PcbCrawler


def test_crawler_find_pcbs(tmp_path):
    """Verify that crawler finds .kicad_pcb files in a directory."""
    # Create fake project structure
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "board1.kicad_pcb").write_text("(kicad_pcb ...)")
    (project_dir / "subdir").mkdir()
    (project_dir / "subdir" / "board2.kicad_pcb").write_text("(kicad_pcb ...)")
    (project_dir / "readme.md").write_text("hello")

    crawler = PcbCrawler(dataset_dir=tmp_path / "dataset")
    pcbs = crawler._find_pcb_files(project_dir)

    assert len(pcbs) == 2
    assert any(p.name == "board1.kicad_pcb" for p in pcbs)
    assert any(p.name == "board2.kicad_pcb" for p in pcbs)

def test_crawler_extract_data(tmp_path, monkeypatch):
    """Verify that crawler extracts netlist and drc labels."""
    from temper_placer.core.netlist import Netlist
    from temper_placer.io.kicad_parser import ParseResult
    from temper_placer.validation.drc import DRCResult

    # Setup test file
    pcb_path = tmp_path / "test.kicad_pcb"
    pcb_path.write_text("(kicad_pcb ...)")

    # Mock parser
    def mock_parse(_path):
        return ParseResult(netlist=Netlist(components=[], nets=[]), board=None, warnings=[])
    monkeypatch.setattr("temper_placer.scale.crawler.parse_kicad_pcb", mock_parse)

    # Mock DRC
    class MockValidator:
        def is_available(self): return True
        def run_drc(self, _path): return DRCResult(success=True, violations=[], error_count=0, warning_count=0)
    monkeypatch.setattr("temper_placer.scale.crawler.KiCadDRCValidator", MockValidator)

    crawler = PcbCrawler(dataset_dir=tmp_path / "dataset")
    crawler._process_pcb(pcb_path, "test_repo")

    assert (tmp_path / "dataset" / "test_repo_test" / "metadata.json").exists()
    assert (tmp_path / "dataset" / "test_repo_test" / "board.kicad_pcb").exists()

