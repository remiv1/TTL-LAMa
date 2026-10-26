#!/usr/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
RESET='\033[0m'
COMPOSE_FILE='compose.test.yml'
LOG_FILE='build.log'
ONLY_SQLITE=false
WITHOUT_OIDC=false
TEST_SELECTOR=''
CONTAINERS_TO_DOWN=''
export PODMAN_COMPOSE_WARNING_LOGS=false

usage() {
  printf 'Usage: %s [--only-sqlite] [--without-oidc] [-t tests.module::test_name]\n' "$0"
}

while (($#)); do
  case "$1" in
    --only-sqlite)
      ONLY_SQLITE=true
      ;;
    --without-oidc)
      WITHOUT_OIDC=true
      ;;
    -t)
      if (($# < 2)) || [[ -z "$2" || "$2" == -* ]]; then
        usage
        exit 2
      fi
      TEST_SELECTOR="$2"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Option inconnue : %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

# Helper to print section headers with colors
section() {
  local color="$1"
  local title="$2"
  len=${#title}
  left_and_right=3
  total=80
  spaces=$(( (total - len - 2 * left_and_right - 2) / 2 ))
  added=$((len % 2))
  printf -- "${color}%*s\n" "$total" '' | tr ' ' '='
  printf "%*s" "$left_and_right" '' | tr ' ' '='
  printf "‖%*s" "${spaces}" ''
  printf "%s" "$title"
  printf "%*s" $((spaces + added)) ''
  printf "‖"
  printf "%*s\n" "$left_and_right" '' | tr ' ' '='
  printf -- "%*s\n${RESET}" "$total" '' | tr ' ' '='
}

# Display the result of a function execution with colored messages
result() {
  # result "function_name" "message_if_ok" "message_if_nok"
  local function_name="$1"
  local if_ok="$2"
  local if_nok="$3"
 $function_name
  code=$?
  if (( code == 0 )); then
    printf "${GREEN}%s${RESET}\n" "$if_ok"
  else
    printf "${RED}%s${RESET}\n" "$if_nok"
  fi
}

build_containers() {
  # Build the containers using podman compose and log the output to a file
  podman compose -f "$COMPOSE_FILE" build > "$LOG_FILE" 2>&1
  code=$?
  if (( code != 0 )); then
    printf "${RED}%s${RESET}\n" "Erreur lors de la construction des conteneurs. Voir $LOG_FILE pour les détails."
    cat "$LOG_FILE"
    rm -f "$LOG_FILE"
    exit "$code"
  fi
}

launch_database() {
  # Launch the database containers using podman compose and log the output to a file
  podman compose -f "$COMPOSE_FILE" up -d postgres mariadb mysql > "$LOG_FILE" 2>&1
  code=$?
  if (( code != 0 )); then
    printf "${RED}%s${RESET}\n" "Erreur lors du lancement des bases de données. Voir $LOG_FILE pour les détails."
    cat "$LOG_FILE"
    rm -f "$LOG_FILE"
    exit "$code"
  fi
  CONTAINERS_TO_DOWN="$CONTAINERS_TO_DOWN postgres mariadb mysql"
}

launch_oidc_provider() {
  # Launch the OIDC provider container using podman compose and log the output to a file
  podman compose -f "$COMPOSE_FILE" up -d dex > "$LOG_FILE" 2>&1
  code=$?
  if (( code != 0 )); then
    printf "${RED}%s${RESET}\n" "Erreur lors du lancement de l'OIDC provider. Voir $LOG_FILE pour les détails."
    cat "$LOG_FILE"
    rm -f "$LOG_FILE"
    exit "$code"
  fi
  CONTAINERS_TO_DOWN="$CONTAINERS_TO_DOWN dex"
}

check_databases_are_up() {
  # Check if the database containers are up and ready
  check_postgres() {
    # Wait until the Postgres container is ready to accept connections
    while ! podman compose -f "$COMPOSE_FILE" exec -T postgres pg_isready -h localhost -p 5432 -U postgres >/dev/null 2>&1; do
      sleep 1
    done
    printf "${GREEN}%s${RESET}\n" "Postgres est prêt."
  }

  check_mariadb() {
    # Wait until the MariaDB container is ready to accept connections
    while ! podman compose -f "$COMPOSE_FILE" exec -T mariadb mariadb-admin ping -h localhost -u root -ptest-only-password >/dev/null 2>&1; do
      sleep 1
    done
    printf "${GREEN}%s${RESET}\n" "MariaDB est prêt."
  }

  check_mysql() {
    # Wait until the MySQL container is ready to accept connections
    while ! podman compose -f "$COMPOSE_FILE" exec -T mysql mysqladmin ping -h localhost -P 3307 -u root --password=root >/dev/null 2>&1; do
      sleep 1
    done
    printf "${GREEN}%s${RESET}\n" "MySQL est prêt."
  }

  check_postgres &
  pid_postgres=$!
  check_mariadb &
  pid_mariadb=$!
  check_mysql &
  pid_mysql=$!
  wait "$pid_postgres"
  wait "$pid_mariadb"
  wait "$pid_mysql"
}

check_oidc_provider() {
  # Check if the OIDC provider is up and ready
  while ! podman compose -f "$COMPOSE_FILE" exec dex wget -q -O /dev/null http://127.0.0.1:5556/dex/healthz > "$LOG_FILE" 2>&1; do
    sleep 1
  done
  printf "${GREEN}%s${RESET}\n" "OIDC Provider est prêt."
}

launch_tests() {
  # Launch only the test container with the requested pytest selection.
  local -a pytest_args=("-v" "--color=yes" "-ra" "-p" "no:cacheprovider")
  local -a compose_args=(run --rm --no-deps)
  if [[ -n "$TEST_SELECTOR" ]]; then
    pytest_args+=("$TEST_SELECTOR")
  fi
  if [[ "$WITHOUT_OIDC" == true ]]; then
    pytest_args+=("-m" "not oidc")
  fi
  if [[ "$ONLY_SQLITE" == true ]]; then
    compose_args+=(-e "TTL_LAMA_TEST_DATABASES=sqlite")
  fi
  podman compose -f "$COMPOSE_FILE" "${compose_args[@]}" tests \
    python -m pytest "${pytest_args[@]}"
  code=$?
  if (( code != 0 )); then
    echo "Erreur lors du lancement des tests. Voir $LOG_FILE pour les détails."
    cat "$LOG_FILE"
    rm -f "$LOG_FILE"
    exit "$code"
  fi
  rm -f "$LOG_FILE"
}

printf "\n"
section "$GREEN" "Construction des conteneurs"
result build_containers "[PODMAN BUILD] Conteneurs construits avec succès." "Échec de la construction des conteneurs."
printf "\n"

section "$BLUE" "Lancement des bases de données"
if [[ "$ONLY_SQLITE" == false ]]; then
  result launch_database "[DATABASES] Bases de données lancées avec succès." "Échec du lancement des bases de données."
else
  printf "${YELLOW}%s${RESET}\n" "[DATABASES] Seule SQLite sera utilisée."
fi
printf "\n"

section "$BLUE" "Lancement de l'OIDC Provider"
if [[ "$WITHOUT_OIDC" == false ]]; then
  result launch_oidc_provider "[OIDC] OIDC Provider lancé avec succès." "Échec du lancement de l'OIDC Provider."
else
  printf "${YELLOW}%s${RESET}\n" "[OIDC] Lancement de Dex ignoré."
fi
printf "\n"

section "$YELLOW" "Vérification des bases de données"
if [[ "$ONLY_SQLITE" == false ]]; then
  result check_databases_are_up "[DATABASES] Bases de données prêtes." "Échec de la vérification des bases de données."
else
  printf "${YELLOW}%s${RESET}\n" "[DATABASES] Vérification des moteurs externes ignorée."
fi
printf "\n"

section "$YELLOW" "Vérification de l'OIDC Provider"
if [[ "$WITHOUT_OIDC" == false ]]; then
  result check_oidc_provider "[OIDC] OIDC Provider prêt." "Échec de la vérification de l'OIDC Provider."
else
  printf "${YELLOW}%s${RESET}\n" "[OIDC] Vérification de Dex ignorée."
fi
printf "\n"

section "$RED" "Lancement des tests"
result launch_tests "[TESTS] Tests exécutés avec succès." "Échec de l’exécution des tests."
printf "\n"

if [[ -n "$CONTAINERS_TO_DOWN" ]]; then
  podman compose -f "$COMPOSE_FILE" down $CONTAINERS_TO_DOWN > /dev/null 2>&1
  code=$?
  if (( code != 0 )); then
    printf "${RED}%s${RESET}\n" "Erreur lors de l'arrêt des conteneurs. Voir $LOG_FILE pour les détails."
    cat "$LOG_FILE"
    rm -f "$LOG_FILE"
    exit "$code"
  else
    printf "${GREEN}%s${RESET}\n" "Conteneurs arrêtés avec succès."
    printf "\n"
  fi
fi
export PODMAN_COMPOSE_WARNING_LOGS=true
