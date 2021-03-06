#!/usr/bin/env bash

if [ -z "${SAQ_HOME}" ]
then
    # the installer should have created a ~/.ace symlink to ace
    if [ -L ~/.ace ]
    then
        export SAQ_HOME=$(readlink -f ~/.ace)
    elif [ -e ace ] && [ -x ace ]
    then
        export SAQ_HOME=$(pwd)
    elif [ -d /opt/ace ]
    then
        export SAQ_HOME=/opt/ace
    else
        echo "cannot determine what SAQ_HOME env var should be"
        exit 1
    fi
fi

# make sure our PATH is set correctly
if [[ ":${PATH}:" != *":${SAQ_HOME}:"* ]]; then
    export PATH="${PATH}:${SAQ_HOME}"
fi

if [[ ":${PATH}:" != *":${SAQ_HOME}/bin:"* ]]; then
    export PATH="${PATH}:${SAQ_HOME}/bin"
fi
