#! /bin/bash
##########################################################################################
#./gradlew f_o_i 
# Remove temporary folders (Only for a clean build)
# chmod +x build.sh
##########################################################################################
rm -rf ./tmp ./build ./external ./.gradle
##########################################################################################
# Download all the component dependencies (this command is included in the f_o_i).
##########################################################################################
./gradlew fwk_retrieve_dependencies --refresh-dependencies
##########################################################################################
# Initialize the toolchains and generate gradle labels
##########################################################################################
./gradlew fwk_optimases_initialize -x fwk_retrieve_dependencies
##########################################################################################
# Check CoDDA (TC0018)
##########################################################################################
# ./gradlew fwk_optimases_generate --action codda_run_check_prelim -x fwk_retrieve_dependencies
./gradlew fwk_optimases_generate --action codda_run_check -x fwk_retrieve_dependencies
##########################################################################################
# Check DCSL (TC0024)
##########################################################################################
./gradlew fwk_optimases_generate --action all_check_design -x fwk_retrieve_dependencies
##########################################################################################
# Generate design documentation
##########################################################################################
#./gradlew fwk_optimases_generate --action codda_gen_html_enhanced -x fwk_retrieve_dependencies
##########################################################################################
# Generate code (.c and .h) and copy to src/main folder (TC0018)
##########################################################################################
./gradlew fwk_optimases_generate --action codda_merge_code -x fwk_retrieve_dependencies
./gradlew fwk_optimases_generate --action codda_import_code -x fwk_retrieve_dependencies
##########################################################################################
# Check code to ensure all rules are being fulfilled (TC0013)
##########################################################################################
./gradlew fwk_optimases_generate --action all_check_code -x fwk_retrieve_dependencies
##########################################################################################
# Check code design (code is written according to what is specified in DCSL)
##########################################################################################
./gradlew fwk_optimases_generate --action check_code_design -x fwk_retrieve_dependencies
##########################################################################################
# Check data and control flow of C code implementing a SUV with its DCSL (TC0021)
##########################################################################################
./gradlew fwk_optimases_generate --action all_check_flow -x fwk_retrieve_dependencies
##########################################################################################
# Make and check build (TC0020)
##########################################################################################
./gradlew fwk_make
./gradlew fwk_optimases_generate --action all_check_build -x fwk_retrieve_dependencies
##########################################################################################
# Unit proof (TC0023)
##########################################################################################
./gradlew fwk_optimases_generate --action all_verif_proof -x fwk_retrieve_dependencies
