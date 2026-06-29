from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult, Issue, Location, Severity
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement


class NoiseCouplingCheck(Check):
    """
    Checks for potential electromagnetic noise coupling.

    Validates distance between 'Aggressor' (noisy) and 'Victim' (sensitive)
    components. Unlike standard DRC clearance, this check applies even
    if components are on different layers, as noise couples through the PCB.
    """

    @property
    def name(self) -> str:
        return "emc_noise_coupling"

    @property
    def category(self) -> str:
        return "emc"

    @property
    def description(self) -> str:
        return "Identify and minimize noise coupling between aggressor and victim components."

    def run(self, placement: Placement, constraints: ConstraintSet) -> CheckResult:
        issues = []
        pairs = placement.all_pairs()

        # We classify coupling based on clearance rules involving specific keywords
        # or just use any clearance rule as an EMC constraint if it involves
        # Aggressor/Victim looking classes.

        NOISY_KEYWORDS = ["power", "clock", "switching", "pwm", "high_freq"]
        SENSITIVE_KEYWORDS = ["analog", "sensor", "small_signal", "victim"]

        for ref_a, ref_b in pairs:
            comp_a = placement.get_component(ref_a)
            comp_b = placement.get_component(ref_b)

            if not comp_a or not comp_b:
                continue

            required_clearance = constraints.get_clearance(comp_a.net_class, comp_b.net_class)

            # If no specific rule, fallback to checking if they fit keywords
            # and may need a default coupling margin?
            # For now, we only act on defined clearance rules.
            if required_clearance <= 0:
                continue

            # Check if this pair is likely an EMC coupling case
            is_noise_case = False
            a_class = comp_a.net_class.lower()
            b_class = comp_b.net_class.lower()

            a_noisy = any(k in a_class for k in NOISY_KEYWORDS)
            b_noisy = any(k in b_class for k in NOISY_KEYWORDS)
            a_sensitive = any(k in a_class for k in SENSITIVE_KEYWORDS)
            b_sensitive = any(k in b_class for k in SENSITIVE_KEYWORDS)

            if (a_noisy and b_sensitive) or (b_noisy and a_sensitive):
                is_noise_case = True

            # If not a specific noise case, we could skip it in THIS check (since DRC_clearance handles it)
            # but usually we want to highlight it if it's an EMC concern.
            # Let's assume ANY clearance rule involving these keywords is an EMC concern.
            if not is_noise_case:
                continue

            dist = comp_a.edge_distance_to(comp_b)

            if dist < required_clearance:
                issues.append(Issue(
                    severity=Severity.WARNING,
                    code=f"{self.code_prefix}001",
                    message=f"Noise coupling risk: {dist:.3f}mm < {required_clearance}mm between {ref_a} ({comp_a.net_class}) and {ref_b} ({comp_b.net_class})",
                    category=self.category,
                    check_name=self.name,
                    affected_items=[ref_a, ref_b],
                    location=Location(
                        x=(comp_a.x + comp_b.x) / 2,
                        y=(comp_a.y + comp_b.y) / 2
                    ),
                    details={
                        "distance_mm": dist,
                        "required_mm": required_clearance,
                        "aggressor": ref_a if a_noisy else ref_b,
                        "victim": ref_b if a_noisy else ref_a
                    }
                ))

        return CheckResult(
            check_name=self.name,
            passed=len(issues) == 0,
            issues=issues
        )
