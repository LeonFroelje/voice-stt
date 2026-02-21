{
  description = "Python devShells";

  nixConfig = {
    extra-substituters = [
      "https://cache.nixos-cuda.org"
      "https://nix-community.cachix.org"
    ];
    extra-trusted-public-keys = [
      "cache.nixos-cuda.org:74DUi4Ye579gUqzH4ziL9IyiJBlDpMRn9MBN8oNan9M="
      "nix-community.cachix.org-1:mB9FSh9qf2dCimDSUo8Zy7bkq5CX+/rkCWyvRCYg3Fs="
    ];
  };

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-unstable";
    nixvim = {
      url = "github:nix-community/nixvim";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    nixvimModules = {
      url = "github:LeonFroelje/nixvim-modules";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      nixvim,
      nixvimModules,
    }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs {
        inherit system;
        config = {
          allowUnfree = true;
          cudaSupport = true;
        };
      };
      python = pkgs.python313;
      apiDependencies = with python.pkgs; [
        fastapi
        uvicorn
        python-multipart
        faster-whisper
        pydantic
        setuptools
        pydantic-settings
        python-dotenv
      ];
    in
    {
      packages.${system} = {
        default = python.pkgs.buildPythonApplication {
          pname = "whisper-api";
          version = "0.1.0";
          pyproject = true;
          src = ./.;

          propagatedBuildInputs = apiDependencies;
        };
      };

      nixosModules.default =
        {
          config,
          lib,
          pkgs,
          ...
        }:
        let
          cfg = config.services.voiceStt;
          defaultPkg = self.packages.${pkgs.system}.default;
        in
        {
          options.services.voiceStt = with lib; {
            enable = lib.mkEnableOption "Voice STT  API Server";

            package = lib.mkOption {
              type = lib.types.package;
              default = defaultPkg;
              description = "The Whisper API package to use.";
            };

            environmentFile = mkOption {
              type = types.nullOr types.path;
              default = null;
              description = "Path to an environment file for secrets/overrides.";
            };

            host = mkOption {
              type = types.str;
              default = "127.0.0.1";
              description = "Hostname or IP to bind the server to.";
            };

            port = mkOption {
              type = types.int;
              default = 8000;
              description = "Port for the FastAPI server.";
            };

            whisperModel = mkOption {
              type = types.str;
              default = "base";
              description = "Whisper model size (base, small, large-v3).";
            };

            device = mkOption {
              type = types.str;
              default = "cuda";
              description = "Compute device (cuda or cpu).";
            };

            modelsDir = mkOption {
              type = types.str;
              default = "/var/lib/whisper-api-models";
              description = "Directory to store downloaded models.";
            };
          };

          config = lib.mkIf cfg.enable {
            systemd.services.whisper-api = {
              description = "Faster-Whisper FastAPI Service";
              wantedBy = [ "multi-user.target" ];
              after = [ "network.target" ];

              environment = {
                WHISPER_HOST = cfg.host;
                WHISPER_PORT = toString cfg.port;
                WHISPER_WHISPER_MODEL = cfg.whisperModel;
                WHISPER_DEVICE = cfg.device;
                WHISPER_MODELS_DIR = cfg.modelsDir;

                # CRITICAL FOR CUDA: Points CTranslate2 to the NixOS NVIDIA drivers
                LD_LIBRARY_PATH = "/run/opengl-driver/lib";
                PYTHONUNBUFFERED = "1";
              };

              serviceConfig = {
                ExecStart = "${cfg.package}/bin/whisper-api";
                EnvironmentFile = lib.mkIf (cfg.environmentFile != null) cfg.environmentFile;

                # State Management
                StateDirectory = "whisper-api-models";

                # Hardening & GPU Permissions
                DynamicUser = true;
                SupplementaryGroups = [
                  "video"
                  "render"
                ];

                # We must disable PrivateDevices so the container can see the GPU
                PrivateDevices = false;
                DeviceAllow = [
                  "/dev/nvidia0 rwm"
                  "/dev/nvidiactl rwm"
                  "/dev/nvidia-uvm rwm"
                  "/dev/nvidia-uvm-tools rwm"
                  "/dev/nvidia-modeset rwm"
                ];
              };
            };
          };
        };

      devShells.${system} = {
        default =
          (pkgs.buildFHSEnv {
            name = "Python dev shell";
            targetPkgs =
              p: with p; [
                fd
                ripgrep
                (nixvimModules.lib.mkNvim [ nixvimModules.nixosModules.python ])
                # Downgraded to 3.11 for ML compatibility (Torch, CTranslate2, etc.)
                (python.withPackages (
                  pypkgs: with pypkgs; [
                    faster-whisper
                    fastapi
                    pydantic
                    pydantic-settings
                    uvicorn
                    python-multipart
                  ]
                ))
                ffmpeg
              ];
            runScript = "zsh";
          }).env;

        uv =
          (pkgs.buildFHSEnv {
            name = "uv-shell";
            targetPkgs =
              p: with p; [
                uv
                zlib
                glib
                openssl
                stdenv.cc.cc.lib
                (nixvimModules.lib.mkNvim [ nixvimModules.nixosModules.python ])
              ];
            runScript = "zsh";

            multiPkgs = p: [
              p.zlib
              p.openssl
            ];
          }).env;
      };
    };
}
