{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.services.fluxdown;
in
{
  options.services.fluxdown = {
    enable = lib.mkEnableOption "FluxDown download server and Web UI";

    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.callPackage ../pkgs/fluxdown-server { };
      defaultText = lib.literalExpression "pkgs.callPackage ../pkgs/fluxdown-server { }";
      description = "FluxDown package containing fluxdown-agent and fluxdownd.";
    };

    listenAddress = lib.mkOption {
      type = lib.types.str;
      default = "127.0.0.1";
      example = "0.0.0.0";
      description = "Listen address for the Web UI and API. Use brackets for IPv6.";
    };

    port = lib.mkOption {
      type = lib.types.port;
      default = 17800;
      description = "TCP port for the Web UI and API.";
    };

    openFirewall = lib.mkEnableOption "opening the Web UI and API port in the firewall";

    environment = lib.mkOption {
      type = lib.types.attrsOf lib.types.str;
      default = { };
      example = {
        FLUXDOWN_LANG = "zh";
        FLUXDOWN_LOG_LEVEL = "warn";
      };
      description = ''
        Additional upstream environment variables. Do not put secrets here;
        use environmentFile instead. Data is stored in /var/lib/fluxdown.
        Custom download directories must be writable by the fluxdown user.
      '';
    };

    environmentFile = lib.mkOption {
      type = lib.types.nullOr (lib.types.strMatching "/.*");
      default = null;
      example = "/run/secrets/fluxdown.env";
      description = ''
        Runtime environment file containing secrets such as FLUXDOWN_TOKEN
        or FLUXDOWN_DATABASE_URL. Keep this file outside the Nix store.
        The access key requires 8 to 128 visible ASCII characters, including
        letters and digits. FLUXDOWN_TOKEN only seeds an unset key unless
        FLUXDOWN_TOKEN_FORCE=1 is also set.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    users.users.fluxdown = {
      isSystemUser = true;
      group = "fluxdown";
      home = "/var/lib/fluxdown";
    };
    users.groups.fluxdown = { };

    networking.firewall.allowedTCPPorts = lib.mkIf cfg.openFirewall [ cfg.port ];

    systemd.services.fluxdown = {
      description = "FluxDown download server";
      wantedBy = [ "multi-user.target" ];
      wants = [ "network-online.target" ];
      after = [ "network-online.target" ];
      environment = lib.mkMerge [
        {
          FLUXDOWN_BIND = "${cfg.listenAddress}:${toString cfg.port}";
          FLUXDOWN_DATA_DIR = "/var/lib/fluxdown";
          FLUXDOWN_SAVE_DIR = lib.mkDefault "/var/lib/fluxdown/downloads";
          FLUXDOWN_ANALYTICS = lib.mkDefault "false";
          FLUXDOWN_MDNS = lib.mkDefault "false";
        }
        cfg.environment
      ];
      serviceConfig = {
        ExecStart = "${lib.getExe' cfg.package "fluxdown-agent"} --server";
        User = "fluxdown";
        Group = "fluxdown";
        StateDirectory = "fluxdown";
        StateDirectoryMode = "0750";
        WorkingDirectory = "/var/lib/fluxdown";
        Restart = "on-failure";
        RestartSec = 5;
        UMask = "0027";
        NoNewPrivileges = true;
        PrivateTmp = true;
        ProtectSystem = "full";
        ProtectHome = true;
      }
      // lib.optionalAttrs (cfg.environmentFile != null) {
        EnvironmentFile = cfg.environmentFile;
      };
    };
  };
}
