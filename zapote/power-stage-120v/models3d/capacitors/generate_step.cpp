// Simple capacitor assembly envelopes built from public dimensions.
// These are not manufacturer CAD or approved mechanical inspection models.
#include <BRep_Builder.hxx>
#include <BRepPrimAPI_MakeBox.hxx>
#include <BRepPrimAPI_MakeCylinder.hxx>
#include <IFSelect_ReturnStatus.hxx>
#include <STEPControl_StepModelType.hxx>
#include <STEPControl_Writer.hxx>
#include <TopoDS_Compound.hxx>
#include <gp_Ax2.hxx>
#include <gp_Dir.hxx>
#include <gp_Pnt.hxx>

#include <filesystem>
#include <fstream>
#include <iostream>
#include <regex>
#include <string>

namespace fs = std::filesystem;

struct Model {
    BRep_Builder builder;
    TopoDS_Compound compound;

    Model() { builder.MakeCompound(compound); }

    void box(double x, double y, double z, double length, double width, double height) {
        builder.Add(compound, BRepPrimAPI_MakeBox(gp_Pnt(x, y, z), length, width, height).Shape());
    }

    void cylinder(double x, double y, double z, double dx, double dy, double dz,
                  double radius, double length) {
        builder.Add(compound,
                    BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x, y, z), gp_Dir(dx, dy, dz)),
                                             radius, length).Shape());
    }

    void save(const fs::path& path) {
        STEPControl_Writer writer;
        writer.Transfer(compound, STEPControl_AsIs);
        if (writer.Write(path.string().c_str()) != IFSelect_RetDone) {
            throw std::runtime_error("Could not write " + path.string());
        }
        // OCC otherwise inserts wall-clock time into every STEP header.
        std::ifstream input(path, std::ios::binary);
        std::string content((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
        const std::regex timestamp("'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}'");
        const std::string stable = std::regex_replace(content, timestamp, "'2026-09-26T00:00:00'");
        if (stable == content) {
            throw std::runtime_error("Missing STEP timestamp in " + path.string());
        }
        std::ofstream output(path, std::ios::binary | std::ios::trunc);
        output << stable;
    }
};

void cde(const fs::path& directory, const std::string& name, double diameter,
         double lead_diameter) {
    Model m;
    const double axis_height = diameter / 2 + 0.6;
    m.cylinder(4.25, 0, axis_height, 1, 0, 0, diameter / 2, 34);
    for (double x : {0.0, 42.5}) {
        m.cylinder(x, 0, 0, 0, 0, 1, lead_diameter / 2, axis_height);
    }
    m.cylinder(0, 0, axis_height, 1, 0, 0, lead_diameter / 2, 4.25);
    m.cylinder(38.25, 0, axis_height, 1, 0, 0, lead_diameter / 2, 4.25);
    m.save(directory / name);
}

void film(const fs::path& directory, const std::string& name, double x0, double y0,
          double length, double width, double height, double pitch_x, double pitch_y,
          double lead_diameter) {
    Model m;
    m.box(x0, y0, 0.5, length, width, height - 0.5);
    for (double x : {0.0, pitch_x}) {
        const int rows = pitch_y == 0 ? 1 : 2;
        for (int row = 0; row < rows; ++row) {
            const double y = row == 0 ? 0 : pitch_y;
            m.cylinder(x, y, 0, 0, 0, 1, lead_diameter / 2, 0.7);
        }
    }
    m.save(directory / name);
}

void murata(const fs::path& directory) {
    Model m;
    // Disc diameter and thickness are specified; stand-off/lead bend are illustrative.
    m.cylinder(5, -2, 9.5, 0, 1, 0, 4.5, 4);
    for (double x : {0.0, 10.0}) {
        m.cylinder(x, 0, 0, 0, 0, 1, 0.3, 7);
    }
    m.save(directory / "Murata_DE1E3RA222MA4BP01F.step");
}

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "Usage: generate_step OUTPUT_DIRECTORY\n";
        return 2;
    }
    const fs::path directory(argv[1]);
    fs::create_directories(directory);
    try {
        cde(directory, "CDE_942C12P22K-F.step", 26.5, 1.2);
        cde(directory, "CDE_942C12P1K-F.step", 19.0, 1.0);
        film(directory, "TDK_B32652A0104K000.step", -1.5, -4.5,
             18, 9, 17.5, 15, 0, 0.8);
        // KiCad model Y grows opposite footprint Y; four pads occupy y=0,20.3.
        film(directory, "TDK_B32656G0275J000.step", -2.25, -26.65,
             42, 33, 48, 37.5, -20.3, 1.2);
        murata(directory);
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
