# Development Instructions

1. Clone the submodules
```bash
mkdir stratus-agent
cd stratus-agent
git clone --recurse-submodules git@github.com:xlab-uiuc/Stratus-agent.git
```

2. Ensure you are in the Python 3.12 environment.
```bash
$ python --version
Python 3.12.x
```
Python 3.12.9 tested.

3. Install dependencies
```bash
pip install uv crewai crewai-tools
crewai install
```
`crewai install` will create the virtual environment in the `.venv` directory. 
You can use `source .venv/bin/activate` to activate the virtual environment.

4. Create a `.env` based on `.env.tmpl` by running:
```bash
cp .env.tmpl .env
```
Update the values here to switch LLM backends.

5. Connect to Kubernetes cluster
If you are testing in AIOpsLab, please follow [this guide](https://github.com/microsoft/AIOpsLab?tab=readme-ov-file#-quick-start-).

If you are testing in ITBench, please follow [this guide](https://github.com/IBM/ITBench-Scenarios/tree/main/sre).

6. (Optional if testing ITBench) Copy and modify `config.yml` file
```bash
cd AIOpsLab/aiopslab
cp config.yml.example config.yml

# Then modify the copied file as you need.
```

7. Modify `.env` for respective bench
In the `.env` file, modify the environment variable `BENCHMARK` to either `ITBench` or `AIOpsLab` according to your need, such as :
```python
BENCHMARK="AIOpsLab"
```

7. Test installation 
For testing the agent on one task of AIOpsLab, run this:
```bash
bash test_agent.sh -r <x86/arm> <task_name>
```

For testing the agent on ITBench, make sure you have deployed the SRE scenario you want to test, then run this:
```bash
bash test_agent.sh -p
```

8. Running evaluations
We currently support running multiple tasks on AIOpsLab in one command.

First, open `eval/eval_tasks.yaml`. You should see similar file content like this:
```yaml
detections:
  - misconfig_app_hotel_res-detection-1
mitigations:
  - k8s_target_port-misconfig-mitigation-1
```

Modify the tasks according to your evaluation needs. If for certain task type, you have no desired tasks, delete the key in the `yaml` file, such as:
```yaml
mitigations:
  - k8s_target_port-misconfig-mitigation-1
```

Then, run the eval script.
```bash
python eval/eval.py
```
