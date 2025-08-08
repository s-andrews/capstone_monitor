THIS_IP=`ifconfig | grep 10.99 | tr -s ' ' | cut -d ' ' -f3`
args=("$@")
PORT=${args[0]}

export OLLAMA_HOST="${THIS_IP}:${PORT}"

echo $OLLAMA_HOST

module load ollama
ollama serve 