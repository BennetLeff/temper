Feature: Component Blocking Behavior
  As a PCB router
  I want to block grid cells occupied by components
  So that traces don't route through component bodies

  Background:
    Given a 100mm x 100mm board with 1mm grid cells

  Scenario: Block component with default margin
    Given a router with default blocking margin
    And a component at position (50.0, 50.0)
    When I block the component on all layers
    Then cell (45, 45) on layer 0 should be blocked
    And cell (45, 45) on layer 1 should be blocked
    And cell (55, 55) on layer 0 should be blocked
    And the blocked area should be 12x12 cells

  Scenario: Block component with reduced margin
    Given a router with 0.1mm blocking margin
    And a component at position (50.0, 50.0)
    When I block the component on all layers
    Then cell (45, 45) on layer 0 should be blocked
    And cell (44, 44) on layer 0 should be free
    And the blocked area should be 11x11 cells

  Scenario: Layer-specific blocking
    Given a router with 0.1mm blocking margin
    And a component at position (50.0, 50.0)
    When I block the component on its actual layer only
    Then cell (50, 50) on layer 0 should be blocked
    And cell (50, 50) on layer 1 should be free

  Scenario: Pin escape routes
    Given a router with 0.1mm blocking margin
    And a component at position (50.0, 50.0)
    When I block the component on all layers
    Then pin 1 should have an escape route of at least 5 cells
    And pin 2 should have an escape route of at least 5 cells
    And pin 3 should have an escape route of at least 5 cells
    And pin 4 should have an escape route of at least 5 cells

  Scenario: Dense component cluster
    Given a router with 0.1mm blocking margin
    And components at positions (30.0, 30.0), (40.0, 30.0), (50.0, 30.0)
    When I block all components on all layers
    Then there should be routing corridors between components
    And all pins should have escape routes of at least 3 cells
