# Initial Plan

I am going to do this in my Fedora, So commands may vary.

#### Python initialization and Some files creation

I am going to use Python 3.12 , so before that some system needs : 

`sudo dnf install -y @development-tools openssl-devel bzip2-devel libffi-devel zlib-devel readline-devel sqlite-devel wget curl git
`

Then, we are going to use pyenv for cleaner build of python : 

```curl https://pyenv.run | bash
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
echo 'export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init --path)"' >> ~/.bashrc
echo 'eval "$(pyenv init -)"' >> ~/.bashrc
exec $SHELL

pyenv install 3.12.0
pyenv local 3.12.0       # do it inside the folder u need

```

Virtual environment intialization,

```
python -m venv venv
source venv/bin/activate
```

Files needed for now,
- .env
- requirements.txt
- .gitignore

For FastAPI,
- Create a folder called app
- Inside that a main.py