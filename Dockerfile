# define the version of Python here
FROM python:3.9.1

# optional labels to provide metadata for the Docker image
# (source: address to the repository, description: human-readable description)
LABEL org.opencontainers.image.source https://github.com/simcesplatform/lfm.git
LABEL org.opencontainers.image.description "Docker image for the Local Flexibility Market (LFM) component."


RUN mkdir -p /lfm
RUN mkdir -p /init
RUN mkdir -p /logs
RUN mkdir -p /domain-messages
RUN mkdir -p /LFMmessages


COPY requirements.txt /requirements.txt
RUN pip install --upgrade pip
RUN pip install -r /requirements.txt

COPY lfm/ /lfm/
COPY init/ /init/
COPY domain-messages/ /domain-messages/
COPY LFMmessages/ /LFMmessages/

WORKDIR /

CMD [ "python3", "-u", "-m", "lfm.component" ]
