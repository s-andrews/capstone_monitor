# This script actually launches the ollama server after
# figuring out which host its running on.  Note that the
# main copy of this script is in the capstone monitor
# folder, but this needs to be copied to 
# /bi/apps/ollama/ to actually run since the user who will
# run this won't have permission to see the primary copy.

THIS_IP=`ifconfig | grep 10.99 | tr -s ' ' | cut -d ' ' -f3`
args=("$@")
PORT=${args[0]}

export OLLAMA_HOST="${THIS_IP}:${PORT}"

export OLLAMA_MODELS=/bi/apps/ollama/models

echo $OLLAMA_HOST

module load ollama
ollama serve 