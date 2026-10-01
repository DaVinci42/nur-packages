{
  pkgs ? import <nixpkgs> { },
}:
let
  inherit (pkgs) lib;
  evaluate =
    extra:
    (import (pkgs.path + "/nixos/lib/eval-config.nix") {
      inherit pkgs;
      system = pkgs.stdenv.hostPlatform.system;
      modules = [
        ../modules/fluxdown.nix
        extra
      ];
    }).config;
  disabled = evaluate { };
  enabled = evaluate { services.fluxdown.enable = true; };
  custom = evaluate {
    services.fluxdown = {
      enable = true;
      package = pkgs.hello;
      listenAddress = "[::1]";
      port = 18000;
      openFirewall = true;
      environment = {
        FLUXDOWN_LANG = "zh";
        FLUXDOWN_ANALYTICS = "true";
        FLUXDOWN_SAVE_DIR = "/srv/downloads";
      };
      environmentFile = "/run/secrets/fluxdown.env";
    };
  };
  conflicts =
    name: value:
    evaluate {
      services.fluxdown = {
        enable = true;
        environment.${name} = value;
      };
    };
  invalidFile = evaluate {
    services.fluxdown = {
      enable = true;
      environmentFile = "relative.env";
    };
  };
  checks = {
    moduleWithoutPkgs = builtins.isPath (import ../default.nix { pkgs = null; }).nixosModules.fluxdown;
    disabledService = !(disabled.systemd.services ? fluxdown);
    disabledUser = !(disabled.users.users ? fluxdown);
    packageDefault = disabled.services.fluxdown.package.pname == "fluxdown-server";
    defaultBind = enabled.systemd.services.fluxdown.environment.FLUXDOWN_BIND == "127.0.0.1:17800";
    firewallClosed = enabled.networking.firewall.allowedTCPPorts == [ ];
    noSecretFile = !(enabled.systemd.services.fluxdown.serviceConfig ? EnvironmentFile);
    privateDefaults =
      enabled.systemd.services.fluxdown.environment.FLUXDOWN_ANALYTICS == "false"
      && enabled.systemd.services.fluxdown.environment.FLUXDOWN_MDNS == "false";
    customBind = custom.systemd.services.fluxdown.environment.FLUXDOWN_BIND == "[::1]:18000";
    firewallOpen = custom.networking.firewall.allowedTCPPorts == [ 18000 ];
    customEnvironment =
      custom.systemd.services.fluxdown.environment.FLUXDOWN_LANG == "zh"
      && custom.systemd.services.fluxdown.environment.FLUXDOWN_ANALYTICS == "true"
      && custom.systemd.services.fluxdown.environment.FLUXDOWN_SAVE_DIR == "/srv/downloads";
    customPackage =
      custom.systemd.services.fluxdown.serviceConfig.ExecStart
      == "${pkgs.hello}/bin/fluxdown-agent --server";
    secretFile =
      custom.systemd.services.fluxdown.serviceConfig.EnvironmentFile == "/run/secrets/fluxdown.env";
    rejectRelativeFile = !(builtins.tryEval invalidFile.services.fluxdown.environmentFile).success;
    rejectBindConflict =
      !(builtins.tryEval (conflicts "FLUXDOWN_BIND" "0.0.0.0:9999")
        .systemd.services.fluxdown.environment.FLUXDOWN_BIND).success;
    rejectDataConflict =
      !(builtins.tryEval (conflicts "FLUXDOWN_DATA_DIR" "/tmp/state")
        .systemd.services.fluxdown.environment.FLUXDOWN_DATA_DIR).success;
  };
  failures = lib.attrNames (lib.filterAttrs (_: passed: !passed) checks);
in
assert lib.assertMsg (failures == [ ]) "Failed checks: ${lib.concatStringsSep ", " failures}";
checks
