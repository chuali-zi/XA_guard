# XA-Guard gVisor static deployment profile

This directory is a Linux-only, opt-in deployment profile. It does not change
`docker-compose.yml`, and repository tests do not install or execute Docker,
gVisor, or `runsc`.

## Prerequisites and runsc installation

- Use a supported x86_64 or aarch64 Linux host with cgroup v2, Docker Engine,
  Compose v2, and a kernel that permits the selected gVisor platform.
- Prefer a dedicated unprivileged account. Rootless Docker must work before
  XA-Guard starts (`docker context use rootless`).
- Install official `runsc` and `containerd-shim-runsc-v1` release artifacts for
  the host architecture. Verify the published SHA-512 checksum, place them at
  `/usr/local/bin/runsc` and `/usr/local/bin/containerd-shim-runsc-v1`, and make
  them root-owned and not group/world writable. Pin and record the release.
- This repository does not download executables or run remote install scripts.
  Follow <https://gvisor.dev/docs/user_guide/install/>.

## Docker runtime registration

Merge `daemon-system.json` into `/etc/docker/daemon.json` for a system daemon,
or merge `daemon-rootless.json` into `~/.config/docker/daemon.json` for rootless
Docker. Do not overwrite unrelated settings. Restart the matching daemon, then:

```sh
docker info --format '{{json .Runtimes}}'
docker run --rm --runtime=runsc --network=none hello-world
```

Both samples retain `runc` as the default. Only workloads that explicitly request
`runsc` change runtime, which limits rollback impact.

## Rootless deployment

The override replaces the rootful `/var/run/docker.sock` source with the current
rootless daemon socket. The API socket must be writable by XA-Guard to create
Gate5 child containers; a read-only bind cannot authorize container creation.
Treat socket access as daemon control and use a dedicated rootless daemon,
account, and host.

```sh
export XA_GUARD_UID="$(id -u)" XA_GUARD_GID="$(id -g)"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
mkdir -p logs/audit logs/runtime
chown -R "$XA_GUARD_UID:$XA_GUARD_GID" logs

docker compose -f docker-compose.yml \
  -f deploy/gvisor/docker-compose.gvisor.yml config
docker compose -f docker-compose.yml \
  -f deploy/gvisor/docker-compose.gvisor.yml up -d --build
```

## Isolation and resource limits

- XA-Guard and the image helper use `runtime: runsc`, non-root IDs, read-only
  roots, `cap_drop: ALL`, `no-new-privileges`, bounded memory/CPU/PIDs, and small
  `noexec` tmpfs mounts.
- The API keeps its Compose network because clients need port 3000. The child
  tool sandbox is the no-egress trust boundary.
- `configs/xa-guard.gvisor.yaml` makes all tools enter Docker isolation and red
  tools select `docker_gvisor`. Existing command construction applies
  `--runtime runsc`, `--network none`, `--read-only`, `--cap-drop ALL`,
  `no-new-privileges`, and memory/CPU/PID limits to child commands.
- Child sandboxes receive no host workspace. Only `logs/` is writable by the API;
  configs and policies are read-only.

These files are static configuration evidence, not proof that this workstation
can run gVisor. Linux runtime, egress denial, syscall isolation, and performance
claims require a separate host acceptance run with archived evidence.

## Rollback

1. Stop this merged profile without deleting logs:

   ```sh
   docker compose -f docker-compose.yml \
     -f deploy/gvisor/docker-compose.gvisor.yml down
   ```

2. Start the unchanged baseline with `docker compose up -d`, or leave it stopped.
3. After confirming no container uses `runsc`, remove only its runtime entry from
   the relevant daemon config, restart that daemon, and verify `runc` remains.
   Keep pinned binaries until the rollback audit closes.
