Feature: Component Blocking Behavior
  As a PCB router
  I want to block grid cells occupied by components
  So that traces don't route through component bodies

  Background:
    Given a 100mm x 100mm board with 1mm grid cells

  Scenario: Block component with default margin
    Given a router with default blocking margin
    And a component at position (50.0, 50.0) with size 10x10
    When I block the component on all layers
    Then cell (45, 45) on layer 0 should be blocked
    And cell (45, 45) on layer 1 should be blocked
    And cell (55, 55) on layer 0 should be blocked
    And the blocked cell count should be 138

  Scenario: Block component with reduced margin
    Given a router with 0.1mm blocking margin
    And a component at position (50.0, 50.0) with size 10x10
    When I block the component on all layers
    Then cell (45, 45) on layer 0 should be blocked
    And cell (44, 44) on layer 0 should be free
    And the blocked cell count should be 98

  Scenario: Layer-specific blocking
    Given a router with 0.1mm blocking margin
    And a component at position (50.0, 50.0) with size 10x10
    When I block the component on its actual layer only
    Then cell (50, 50) on layer 0 should be blocked
    And cell (50, 50) on layer 1 should be free

  Scenario: Pin escape routes
    Given a router with 0.1mm blocking margin
    And a component at position (50.0, 50.0) with size 10x10
    And the component has pins at offsets (5, 0), (-5, 0), (0, 5), (0, -5)
    When I block the component on all layers
    Then pin (55, 50) should have an escape route of at least 2 cells
    And pin (45, 50) should have an escape route of at least 2 cells
    And pin (50, 55) should have an escape route of at least 2 cells
    And pin (50, 45) should have an escape route of at least 2 cells

  Scenario: Dense component cluster
    Given a router with 0.1mm blocking margin
    And components at positions (30.0, 30.0), (40.0, 30.0), (50.0, 30.0) with size 8x8
    When I block all components on all layers
    Then there should be routing corridors between components
    And all pins should have escape routes of at least 2 cells