# Custom AzureML environment for the validation framework.
#
# Replace the Julia/tooling installation and validate.sh with
# your actual test framework and dependencies.
# ------------------------------------------------------------------

FROM mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04

# ---- 1. OS packages ------------------------------------------------
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ---- 2. Julia runtime (pinned version) -----------------------------
# Replace with the Julia version your framework requires.
ARG JULIA_VERSION=1.10.2
RUN wget -qO- "https://julialang-s3.julialang.org/bin/linux/x64/${JULIA_VERSION%.*}/julia-${JULIA_VERSION}-linux-x86_64.tar.gz" \
    | tar -xz -C /opt && \
    ln -s /opt/julia-${JULIA_VERSION}/bin/julia /usr/local/bin/julia

# ---- 3. Python packages --------------------------------------------
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# ---- 4. Julia packages (placeholder) -------------------------------
# Uncomment and add your Julia packages here, e.g.:
# RUN julia -e 'using Pkg; Pkg.add(["PackageA", "PackageB"])'

# ---- 5. Test framework / tooling -----------------------------------
# Copy the placeholder validation script into the image.
# In production, replace this with your actual test framework binary
# or install it via package manager above.
COPY validate.sh /opt/validation/validate.sh
RUN chmod +x /opt/validation/validate.sh

# ---- 6. Working directory -------------------------------------------
WORKDIR /opt/validation
