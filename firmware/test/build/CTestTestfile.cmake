# CMake generated Testfile for 
# Source directory: /Users/bennet.leff/Documents/temper/firmware/test
# Build directory: /Users/bennet.leff/Documents/temper/firmware/test/build
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
add_test(all_tests "/Users/bennet.leff/Documents/temper/firmware/test/build/test_runner")
set_tests_properties(all_tests PROPERTIES  _BACKTRACE_TRIPLES "/Users/bennet.leff/Documents/temper/firmware/test/CMakeLists.txt;180;add_test;/Users/bennet.leff/Documents/temper/firmware/test/CMakeLists.txt;0;")
add_test(state_machine_tests "/Users/bennet.leff/Documents/temper/firmware/test/build/test_state_machine_only")
set_tests_properties(state_machine_tests PROPERTIES  _BACKTRACE_TRIPLES "/Users/bennet.leff/Documents/temper/firmware/test/CMakeLists.txt;181;add_test;/Users/bennet.leff/Documents/temper/firmware/test/CMakeLists.txt;0;")
add_test(pid_tests "/Users/bennet.leff/Documents/temper/firmware/test/build/test_pid_only")
set_tests_properties(pid_tests PROPERTIES  _BACKTRACE_TRIPLES "/Users/bennet.leff/Documents/temper/firmware/test/CMakeLists.txt;182;add_test;/Users/bennet.leff/Documents/temper/firmware/test/CMakeLists.txt;0;")
add_test(safety_tests "/Users/bennet.leff/Documents/temper/firmware/test/build/test_safety_only")
set_tests_properties(safety_tests PROPERTIES  _BACKTRACE_TRIPLES "/Users/bennet.leff/Documents/temper/firmware/test/CMakeLists.txt;183;add_test;/Users/bennet.leff/Documents/temper/firmware/test/CMakeLists.txt;0;")
add_test(pan_detection_tests "/Users/bennet.leff/Documents/temper/firmware/test/build/test_pan_detection_only")
set_tests_properties(pan_detection_tests PROPERTIES  _BACKTRACE_TRIPLES "/Users/bennet.leff/Documents/temper/firmware/test/CMakeLists.txt;184;add_test;/Users/bennet.leff/Documents/temper/firmware/test/CMakeLists.txt;0;")
add_test(pll_tests "/Users/bennet.leff/Documents/temper/firmware/test/build/test_pll_only")
set_tests_properties(pll_tests PROPERTIES  _BACKTRACE_TRIPLES "/Users/bennet.leff/Documents/temper/firmware/test/CMakeLists.txt;185;add_test;/Users/bennet.leff/Documents/temper/firmware/test/CMakeLists.txt;0;")
add_test(integration_tests "/Users/bennet.leff/Documents/temper/firmware/test/build/test_integration_only")
set_tests_properties(integration_tests PROPERTIES  _BACKTRACE_TRIPLES "/Users/bennet.leff/Documents/temper/firmware/test/CMakeLists.txt;186;add_test;/Users/bennet.leff/Documents/temper/firmware/test/CMakeLists.txt;0;")
