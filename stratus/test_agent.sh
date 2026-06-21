#!/usr/bin/env bash
# TODO: convert this to a python script

set -e

preserve_cluster='false'
unit_test='false'
setup_cluster_only='false'
arch=''
output_dir=''

function detect_architecture() {
  arch="$(uname -m)"
  if [[ "$arch" = x86_64* ]]; then
    if [[ "$(uname -a)" = *ARM64* ]]; then
      arch='arm'
    else
      arch='x86'
    fi
  elif [[ "$arch" = i*86 ]]; then
    arch='x86'
  elif [[ "$arch" = arm* ]]; then
    arch='arm'
  elif test "$arch" = aarch64; then
    arch='arm'
  else
    arch='unknown'
  fi

  # echo "Detected architecture: $arch"
}

function show_help() {
  echo "Usage: $0 ([-h]) [-p] [-r <arch>] ([-t] / [-s] / [-d <output_dir>] <task_name>)"
  echo "Options:"
  echo "  -h              Show this help message"
  echo "  -p              Use existing cluster instead of creating a new one"
  echo "  -r <arch>       Specify the architecture (x86 or arm)"
  echo "  -t              Run unit tests"
  echo "  -s              Setup the cluster only, without running the task"
  echo "  -d <output_dir> Specify the output directory (default: eval/\${current_date_time}-\${task_name})"
}

function error() {
  echo -e "\e[31mError: $1\e[0m" >&2
  show_help
  exit 1
}

function set_architecture() {
  case "$1" in
    x86) arch='x86' ;;
    arm) arch='arm' ;;
    *) error "Invalid architecture: $1. Use 'x86' or 'arm'." ;;
  esac
}

function setup_cluster() {
  echo "=== Deleting existing kind cluster ==="
  kind delete cluster --name kind
  echo "=== Creating kind cluster ==="
  kind create cluster --config ./AIOpsLab/kind/kind-config-${arch}.yaml
}

detect_architecture

while getopts 'hpr:td:s' flag; do
  case "${flag}" in
    p) preserve_cluster='true' ;;
    t) unit_test='true' ;;
    r) set_architecture ${OPTARG} ;;
    d) output_dir="${OPTARG}" ;;
    h) show_help && exit 0 ;;
    s) setup_cluster_only='true' ;;
    *) error "Unexpected option ${flag}" ; 
  esac
done

if [[ "$setup_cluster_only" == "true" ]]; then
  setup_cluster
  exit 0
fi

shift $(($OPTIND - 1))
task_name=$1

if [[ $# -gt 1 ]]; then
  error "Too many arguments provided. Only one task_name is allowed."
fi

if [[ -z "$task_name" && "$unit_test" == "false" ]]; then
  task_name='itbench'
  echo "No task name provided. Defaulting to 'itbench'."
fi

if [[ -z "$output_dir" ]]; then
  current_date_time=$(date +"%m-%d_%H-%M-%S")
  output_dir="eval/${current_date_time}-${task_name}"
fi

if [[ "$preserve_cluster" == "false" && "$unit_test" == "false" ]]; then
  setup_cluster
fi

# ========== StratusAgent setup ==========
CURRENT_PATH=$(pwd)
AIOPSLAB_PATH=$CURRENT_PATH/AIOpsLab
STRATUS_PATH=$CURRENT_PATH/src
export TASK_NAME=$task_name
export KUBECONFIG=$HOME/.kube/config
export PYTHONPATH=${CURRENT_PATH}:${AIOPSLAB_PATH}:${STRATUS_PATH}:$PYTHONPATH

if [[ "$unit_test" == "true" ]]; then
  echo "=== Running unit tests ==="
  uv run ./test/test.py
  exit 0
fi

mkdir -p ${output_dir}
mkdir -p ${output_dir}/stratus_output
# ========== StratusAgent execution ==========
echo "=== Cleaning crewAI memories ==="
export OUTPUT_DIRECTORY=${output_dir}/stratus_output
crewai reset-memories -a 2>&1 | tee ${output_dir}/crewai-reset-mem.log 
echo "=== Running crewAI and store all stdout/stderrs ==="
crewai run 2>&1 | tee ${output_dir}/run.log

# ========== Result processing ==========
echo "=== Running log cleaning script ==="
python3 ./eval/clean_asci_color_from_log.py ${output_dir}/crewai-reset-mem.log
python3 ./eval/clean_asci_color_from_log.py ${output_dir}/run.log
