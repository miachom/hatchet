
# Installation without license
1. Follow the standard installation process with conda as 
`conda install hatchet`
2. Also install the following-
`conda install tabix picard mosdepth`
`conda install shapeit -c dranew`

3. As DFCI cannot get Gurobi license because its not considered academic, hatchet is installed with a different Pyomo-supported solver instead of using Gurobi. This might make the hatchet run slower as compared to using Gurobi according to their documentation.
4. Install `cbc` or `glpk` with conda. Here, I am using glpk as `conda install -c conda-forge glpk`
5. Set the Pyomo-supported solver by setting environment variable `HATCHET_COMPUTE_CN_SOLVER` to `cbc` or `glpk` as `export HATCHET_COMPUTE_CN_SOLVER=glpk`
6. Next change solver path in .ini file as `solver=glpk`
7. Running as stdout with `hatchet` environment
`conda activate hatchet`
`hatchet run config.ini`

## Note- mosdepth may require update if the latest is not installed properly and it is dependent on htslib

