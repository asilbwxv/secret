
#./gradlew f_o_i 

#f_o_i
#./gradlew fwk_retrieve_dependencies --refresh-dependencies
 
#./gradlew fwk_optimases_initialize -x fwk_retrieve_dependencies
 
#f_o_g make
#./gradlew fwk_make -x fwk_retrieve_dependencies
 
#build env
#./gradlew fwk_optimases_generate --action=genTIenv --opt="-j 12" -x fwk_retrieve_dependencies
 
#TC TITV
#./gradlew fwk_optimases_labels --toolchain toolchain-TITV
 
#ClientInterface
#./gradlew fwk_optimases_gen --action verif_titv_V_FT_C00267_InterfaceClient_00010_31

./gradlew fwk_optimases_gen --action verif_titv_V_FT_C00267_InterfaceClient_00010_41
