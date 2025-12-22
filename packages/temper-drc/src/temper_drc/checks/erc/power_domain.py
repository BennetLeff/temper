from temper_drc.core.check import Check
from temper_drc.core.result import CheckResult, Issue, Severity
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import Placement


class PowerDomainCheck(Check):
    """
    Checks for voltage domain conflicts.
    
    Ensures that components connected to the same net do not have
    conflicting voltage domains (e.g., 3.3V and 5.0V on the same net).
    Components with 'None' domain are considered generic and ignored.
    """
    
    @property
    def name(self) -> str:
        return "erc_power_domain"

    @property
    def category(self) -> str:
        return "erc"

    @property
    def description(self) -> str:
        return "Identify nets connecting components from different voltage domains."

    def run(self, placement: Placement, constraints: ConstraintSet) -> CheckResult:
        issues = []
        
        for net_name, comp_refs in placement.nets.items():
            domains_on_net = {} # domain -> list of refs
            
            for ref in comp_refs:
                comp = placement.get_component(ref)
                if comp and comp.voltage_domain:
                    domain = comp.voltage_domain
                    if domain not in domains_on_net:
                        domains_on_net[domain] = []
                    domains_on_net[domain].append(ref)
            
            if len(domains_on_net) > 1:
                # Conflict detected
                domain_list = sorted(domains_on_net.keys())
                message = f"Voltage domain conflict on net '{net_name}': domains observed: {', '.join(domain_list)}."
                
                issues.append(Issue(
                    severity=Severity.ERROR,
                    code=f"{self.code_prefix}001",
                    message=message,
                    category=self.category,
                    check_name=self.name,
                    affected_items=comp_refs,
                    location=None,
                    details={
                        "net_name": net_name,
                        "domains": domains_on_net
                    }
                ))
                
        return CheckResult(
            check_name=self.name,
            passed=len(issues) == 0,
            issues=issues
        )
