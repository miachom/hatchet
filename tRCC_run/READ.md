
# Installation without license
1. Follow the standard installation process with conda or miniconda as 
`conda install hatchet`

2. As DFCI cannot get Gurobi license because its not considered academic, hatchet is installed with a different Pyomo-supported solver instead of using Gurobi. This might make the hatchet run slower as compared to using Gurobi according to their documentation.
3. Set the Pyomo-supported solver by setting environment variable `HATCHET_COMPUTE_CN_SOLVER` to `cbc` or `glpk`. In this installation `glpk` is used as 

