# -------------------------
# STAGE 1: Build with tools
# -------------------------
FROM python:3.10.3-slim-bullseye

RUN apt-get -y update
RUN apt-get install -y --fix-missing \
    build-essential \
    cmake \
    gfortran \
    git \
    wget \
    curl \
    graphicsmagick \
    libgraphicsmagick1-dev \
    libatlas-base-dev \
    libavcodec-dev \
    libavformat-dev \
    libgtk2.0-dev \
    libjpeg-dev \
    liblapack-dev \
    libswscale-dev \
    pkg-config \
    python3-dev \
    python3-numpy \
    software-properties-common \
    zip \
    && apt-get clean && rm -rf /tmp/* /var/tmp/*

RUN cd ~ && \
    mkdir -p dlib && \
    git clone -b 'v19.9' --single-branch https://github.com/davisking/dlib.git dlib/ && \
    cd  dlib/ && \
    python3 setup.py install --yes USE_AVX_INSTRUCTIONS


# WORKDIR /app
# COPY . .

# # Install your Python dependencies
# RUN pip3 install --upgrade pip setuptools wheel
# RUN pip3 install -r requirements.txt

# # -------------------------
# # STAGE 2: Runtime image
# # -------------------------
# FROM python:3.10.3-slim-bullseye

# WORKDIR /app

# # Copy installed packages from build stage
# COPY --from=build /usr/local/lib/python3.10 /usr/local/lib/python3.10
# COPY --from=build /usr/local/bin /usr/local/bin
# COPY --from=build /usr/local/include /usr/local/include
# COPY --from=build /usr/local/share /usr/local/share

# # Copy app code
# COPY . .

# EXPOSE 8000
# CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
# Copy your FastAPI project
COPY . /app
WORKDIR /app

# Install Python requirements
RUN pip3 install --upgrade pip
RUN pip3 install -r requirements.txt

# Expose port for uvicorn
EXPOSE 8000

# Run your FastAPI app with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]