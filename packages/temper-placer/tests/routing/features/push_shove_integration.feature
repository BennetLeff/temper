Feature: Push-and-Shove Router Integration
  As a PCB designer
  I want to route nets with push-and-shove capability
  So that I can achieve 100% routing completion

  Background:
    Given a 100mm x 100mm board with 0.5mm grid
    And 2 routing layers (Top and Bottom)

  Scenario: Simple 2-pin net routing
    Given an empty board
    And a net "NET1" with pins at (10.0, 10.0) and (90.0, 90.0)
    When I route the net
    Then the routing should succeed
    And the path should be connected
    And there should be no DRC violations

  Scenario: Multi-pin star topology
    Given an empty board
    And a net "VCC" with pins at:
      | x    | y    |
      | 50.0 | 50.0 |
      | 30.0 | 30.0 |
      | 70.0 | 30.0 |
      | 30.0 | 70.0 |
      | 70.0 | 70.0 |
    When I route the net using star topology
    Then the routing should succeed
    And all pins should be connected
    And the total wirelength should be minimal

  Scenario: Crossing nets without collision
    Given an empty board
    And a net "H_NET" with pins at (10.0, 50.0) and (90.0, 50.0)
    And a net "V_NET" with pins at (50.0, 10.0) and (50.0, 90.0)
    When I route "H_NET" first
    And I route "V_NET" second
    Then both nets should be routed successfully
    And there should be no collisions between nets
    And clearance rules should be satisfied

  Scenario: Push existing trace to make room
    Given a board with net "NET1" routed horizontally at y=50.0
    And a new net "NET2" that needs to cross at (50.0, 50.0)
    When I route "NET2" with push-and-shove enabled
    Then "NET2" should be routed successfully
    And "NET1" should be pushed aside
    And both nets should maintain connectivity
    And clearance should be maintained

  Scenario: Shove multiple traces
    Given a board with 3 parallel nets routed horizontally
    And a new net "CROSS" that needs to cross all 3
    When I route "CROSS" with push-and-shove enabled
    Then "CROSS" should be routed successfully
    And all 3 existing nets should be shoved
    And all nets should maintain connectivity
    And no DRC violations should exist

  Scenario: Dense component cluster routing
    Given a board with 10 components in a 20mm x 20mm area
    And 15 nets connecting these components
    When I route all nets with push-and-shove
    Then at least 90% of nets should be routed
    And DRC violations should be less than 10
    And all routed nets should be connected

  Scenario: Via insertion for layer change
    Given a board with an obstacle blocking the direct path on layer 1
    And a net "NET1" that needs to route through the obstacle area
    When I route "NET1" with via insertion enabled
    Then the routing should succeed
    And the path should use a via to change layers
    And the via count should be minimal (≤ 2)

  Scenario: Path optimization after routing
    Given a board with a routed net containing unnecessary bends
    When I optimize the path
    Then the path length should decrease
    And the path should have fewer segments
    And connectivity should be preserved
    And no new DRC violations should be introduced

  Scenario: Routing with clearance constraints
    Given a board with high-voltage and low-voltage nets
    And clearance rules: HV-LV = 2.0mm, LV-LV = 0.2mm
    When I route all nets
    Then all clearance rules should be satisfied
    And HV nets should maintain 2.0mm clearance from LV nets
    And LV nets should maintain 0.2mm clearance from each other

  Scenario: Incremental routing with state persistence
    Given a partially routed board with 10 nets completed
    When I save the routing state
    And I route 5 more nets
    And I load the saved state
    Then the board should match the original 10-net state
    And I can resume routing from that point
