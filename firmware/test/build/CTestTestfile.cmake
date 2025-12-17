# CMake generated Testfile for 
# Source directory: /Users/bennet/Desktop/temper/firmware/test
# Build directory: /Users/bennet/Desktop/temper/firmware/test/build
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
add_test(all_tests "/Users/bennet/Desktop/temper/firmware/test/build/test_runner")
set_tests_properties(all_tests PROPERTIES  _BACKTRACE_TRIPLES "/Users/bennet/Desktop/temper/firmware/test/CMakeLists.txt;258;add_test;/Users/bennet/Desktop/temper/firmware/test/CMakeLists.txt;0;")
add_test(state_machine_tests "/Users/bennet/Desktop/temper/firmware/test/build/test_state_machine_only")
set_tests_properties(state_machine_tests PROPERTIES  _BACKTRACE_TRIPLES "/Users/bennet/Desktop/temper/firmware/test/CMakeLists.txt;259;add_test;/Users/bennet/Desktop/temper/firmware/test/CMakeLists.txt;0;")
add_test(pid_tests "/Users/bennet/Desktop/temper/firmware/test/build/test_pid_only")
set_tests_properties(pid_tests PROPERTIES  _BACKTRACE_TRIPLES "/Users/bennet/Desktop/temper/firmware/test/CMakeLists.txt;260;add_test;/Users/bennet/Desktop/temper/firmware/test/CMakeLists.txt;0;")
add_test(low_temp_tests "/Users/bennet/Desktop/temper/firmware/test/build/test_low_temp_only")
set_tests_properties(low_temp_tests PROPERTIES  _BACKTRACE_TRIPLES "/Users/bennet/Desktop/temper/firmware/test/CMakeLists.txt;261;add_test;/Users/bennet/Desktop/temper/firmware/test/CMakeLists.txt;0;")
add_test(safety_tests "/Users/bennet/Desktop/temper/firmware/test/build/test_safety_only")
set_tests_properties(safety_tests PROPERTIES  _BACKTRACE_TRIPLES "/Users/bennet/Desktop/temper/firmware/test/CMakeLists.txt;262;add_test;/Users/bennet/Desktop/temper/firmware/test/CMakeLists.txt;0;")
add_test(pan_detection_tests "/Users/bennet/Desktop/temper/firmware/test/build/test_pan_detection_only")
set_tests_properties(pan_detection_tests PROPERTIES  _BACKTRACE_TRIPLES "/Users/bennet/Desktop/temper/firmware/test/CMakeLists.txt;263;add_test;/Users/bennet/Desktop/temper/firmware/test/CMakeLists.txt;0;")
add_test(pll_tests "/Users/bennet/Desktop/temper/firmware/test/build/test_pll_only")
set_tests_properties(pll_tests PROPERTIES  _BACKTRACE_TRIPLES "/Users/bennet/Desktop/temper/firmware/test/CMakeLists.txt;264;add_test;/Users/bennet/Desktop/temper/firmware/test/CMakeLists.txt;0;")
add_test(integration_tests "test_integration_only")
set_tests_properties(integration_tests PROPERTIES  _BACKTRACE_TRIPLES "/Users/bennet/Desktop/temper/firmware/test/CMakeLists.txt;265;add_test;/Users/bennet/Desktop/temper/firmware/test/CMakeLists.txt;0;")
