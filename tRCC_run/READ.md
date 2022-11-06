
# Installation and run without license
1. Follow the standard installation process with conda as 
`conda install hatchet`
2. Also install the following-
`conda install tabix picard mosdepth`
`conda install shapeit -c dranew`

3. If Gurobi license isn't available, hatchet is installed with a different Pyomo-supported solver instead of using Gurobi. This might make the hatchet run slower as compared to using Gurobi according to their documentation. Or alternatively you can try getting your own Gurobi license for invidual use on a specific system or machine.
4. Install `cbc` or `glpk` with conda. Here, I am using glpk as `conda install -c conda-forge glpk`
5. Set the Pyomo-supported solver by setting environment variable `HATCHET_COMPUTE_CN_SOLVER` to `cbc` or `glpk` as


`export HATCHET_COMPUTE_CN_SOLVER=glpk`


7. Next change solver path in .ini file as `solver=glpk`
8. Running as stdout with `hatchet` environment as

`conda activate hatchet`

`module load /path/to/samtools`

`module load /path/to/bcftools`

`module load /path/to/htslibs`

`hatchet run config.ini`

Note- 

mosdepth may require update if the latest is not installed properly and it is dependent on htslib

# Installation and run with Gurobi license

1. If Gurobi license is available, set the solver by setting environment variable `HATCHET_COMPUTE_CN_SOLVER` to `gurobi`
2. And `export GRB_LICENSE_FILE="/path/to/gurobi/gurobi952/gurobi.lic"
3. And run a shell script submitted as a job with all the required modules and steps described above in step 8.
