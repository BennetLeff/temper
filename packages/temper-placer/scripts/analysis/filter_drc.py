
import json

def filter_report():
    try:
        with open('drc_report_v6_fixed.json') as f:
            data = json.load(f)
            
        violations = data.get('violations', [])
        
        routing_violations = []
        mechanical_violations = []
        
        ignored_keywords = [
            "Board edge",
            "Hole clearance",
            "Drilled hole",
            "footprint library",
            "does not match copy",
            "Rear solder mask"
        ]
        
        for v in violations:
            desc = v.get('description', '')
            if any(k in desc for k in ignored_keywords):
                mechanical_violations.append(v)
            else:
                routing_violations.append(v)
                
        print(f"Total Violations: {len(violations)}")
        print(f"Mechanical/Setup Violations: {len(mechanical_violations)}")
        print(f"Routing/Clearance Violations: {len(routing_violations)}")
        
        print("\nRouting Violation Sample:")
        for v in routing_violations[:5]:
            print(f"- {v.get('description')}")
            
    except Exception as e:
        print(e)

if __name__ == "__main__":
    filter_report()
