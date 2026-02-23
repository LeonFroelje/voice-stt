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
        faster-whisper
        pydantic
        setuptools
        pydantic-settings
        python-dotenv
        aiomqtt
        boto3
      ];
    in
    {
      packages.${system} = {
        default = python.pkgs.buildPythonApplication {
          pname = "whisper-worker";
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
            enable = lib.mkEnableOption "Whisper Transcription Worker";

            package = lib.mkOption {
              type = lib.types.package;
              default = defaultPkg;
              description = "The Whisper worker package to use.";
            };

            environmentFile = mkOption {
              type = types.nullOr types.path;
              default = null;
              description = ''
                Path to an environment file for secrets/overrides.
                To prevent leaks, this file should contain:
                - WHISPER_S3_SECRET_KEY
                - WHISPER_MQTT_PASSWORD (if your broker requires auth)
              '';
            };

            # --- MQTT Connection ---
            mqttHost = mkOption {
              type = types.str;
              default = "localhost";
              description = "Mosquitto broker IP/Hostname";
            };

            mqttPort = mkOption {
              type = types.int;
              default = 1883;
              description = "Mosquitto broker port";
            };

            mqttUser = mkOption {
              type = types.nullOr types.str;
              default = null;
              description = "Username used to authenticate with MQTT broker";
            };

            # --- Object Storage (S3 Compatible) ---
            s3Endpoint = mkOption {
              type = types.str;
              default = "http://localhost:3900";
              description = "URL to S3 storage";
            };

            s3AccessKey = mkOption {
              type = types.str;
              default = "your-access-key";
              description = "S3 Access Key";
            };

            s3Bucket = mkOption {
              type = types.str;
              default = "voice-commands";
              description = "S3 Bucket Name";
            };

            # --- Model Settings ---
            whisperModel = mkOption {
              type = types.str;
              default = "small";
              description = "Whisper model size (tiny, base, small, medium, large-v3).";
            };

            device = mkOption {
              type = types.str;
              default = "cuda";
              description = "Compute device (cuda, cpu, or auto).";
            };

            modelsDir = mkOption {
              type = types.str;
              default = "/var/lib/whisper-models";
              description = "Directory to store downloaded Hugging Face and CTranslate2 models.";
            };

            # --- System ---
            logLevel = mkOption {
              type = types.str;
              default = "INFO";
              description = "Logging Level (DEBUG, INFO, WARNING, ERROR)";
            };
          };

          config = lib.mkIf cfg.enable {
            systemd.services.voice-stt = {
              description = "Faster-Whisper Transcription Worker";
              wantedBy = [ "multi-user.target" ];
              after = [ "network.target" ];

              environment =
                let
                  env = {
                    WHISPER_MQTT_HOST = cfg.mqttHost;
                    WHISPER_MQTT_PORT = toString cfg.mqttPort;
                    WHISPER_MQTT_USER = cfg.mqttUser;

                    WHISPER_S3_ENDPOINT = cfg.s3Endpoint;
                    WHISPER_S3_ACCESS_KEY = cfg.s3AccessKey;
                    WHISPER_S3_BUCKET = cfg.s3Bucket;

                    WHISPER_WHISPER_MODEL = cfg.whisperModel;
                    WHISPER_DEVICE = cfg.device;
                    WHISPER_MODELS_DIR = cfg.modelsDir;
                    WHISPER_LOG_LEVEL = cfg.logLevel;

                    # CRITICAL FOR CUDA: Points CTranslate2 to the NixOS NVIDIA drivers
                    LD_LIBRARY_PATH = "/run/opengl-driver/lib";
                    PYTHONUNBUFFERED = "1";
                  };
                in
                lib.filterAttrs (n: v: v != null) env;

              serviceConfig = {
                # Update this if your binary name is still `whisper-api`
                ExecStart = "${cfg.package}/bin/voice-stt";
                EnvironmentFile = lib.mkIf (cfg.environmentFile != null) cfg.environmentFile;

                # State Management
                StateDirectory = cfg.modelsDir;

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
