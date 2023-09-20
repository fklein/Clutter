#!/usr/bin/env bash

set -o errexit
set -o pipefail
# set -o xtrace

shopt -s extglob

readonly __dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly __file="${__dir}/$(basename "${BASH_SOURCE[0]}")"
readonly __base="$(basename "${__file}" .sh)"


# Ausgabe des Hilfe-Texts für den Aufruf des Scripts
show_help() {
    local helpstring="\
        usage: $(basename "${__file}") [OPTIONS] PARTITION ...

        Die Export-Dateien aus OSX (Treasury) für die Archivierung in CMIO erzeugen.

        Die Parameter sind:
            PARTITION
                Eine Liste von Tabellen-Partitionen (Stichtage), für welche der Export erfolgen soll.
                Die Partition sind üblicherweise nach dem Schema T_{YYYY}_{MM}_{DD} benannt.
                Sollen viele Partitionen exportiert werden, ist es aus Performance-Sicht sinnvoll,
                dies auf mehrere parallel laufende Instanzen aufzuteilen.

        Zulässige Optionen sind:
            -o, --output=DIRECTORY
                Das Zielverzeichnis für die Export-Dateien. Erfolgt keine Angabe, werden die Dateien im
                aktuellen Verzeichnis abgelegt.

            -f, --force
                Bereits existierende Ausgabedateien überschreiben.

            -s, --sqlinfo
                Zu jeder Ausgabedatei eine Datei mit dem zugrundeliegenden SQL-Statement erzeugen.

            -v, --verbose
                Verbose-Modus einschalten.

            -t, --trace
                Trace-Modus einschalten.

            -h, --help
                Diesen Hilfetext ausgeben.
    "
    echo "${helpstring}" | sed -r 's/^[[:space:]]{8}//' | sed -r 's/[[:space:]]*$//'
}


# Die Argumente parsen
opts="o:fsvth"
longopts="output:,force,sqlinfo,verbose,trace,help"
args=$(getopt -n "${__base}" -o "${opts}" -l "${longopts}" -- "${@}") || {
    echo >&2
    show_help >&2
    exit 1
}
eval set -- "${args}"
unset outputdir force sqlinfo
while true; do
    case "$1" in
        "--")
            shift
            break
            ;;
        "--output" | "-o" )
            shift
            outputdir="$1"
            ;;
        "--force" | "-f" )
            force=true
            ;;
        "--sqlinfo" | "-s" )
            sqlinfo=true
            ;;
        "--verbose" | "-v" )
            set -o verbose
            ;;
        "--trace" | "-t" )
            set -o xtrace
            ;;
        "--help" | "-h" )
            show_help
            exit 0
            ;;
    esac
    shift
done
if (( $# < 1 )); then
    echo -e "Fehler: Es wurde keine Partition angegeben!\n" >&2
    show_help >&2
    exit 2
fi
PARTITIONS=("$@")


# Hilfsfunktion zum verschönern von Terminal-Output
# Usage: colorize [format,...] ... -- [text] ...
[[ -t 1 ]] && istty=true
colorize() {
    local escapecodes
    declare -A escapecodes=(
        # Common
        [reset]=$'\e[0m' [bold]=$'\e[1m' [dim]=$'\e[2m' [italic]=$'\e[3m' [underline]=$'\e[4m'
        [blink]=$'\e[5m' [invert]=$'\e[7m' [invisible]=$'\e[8m' [strikethrough]=$'\e[9m'
        # Text
        [default]=$'\e[39m'
        [black]=$'\e[30m'   [white]=$'\e[97m'
        [gray]=$'\e[90m'    [lightgray]=$'\e[37m'
        [red]=$'\e[31m'     [lightred]=$'\e[91m'
        [green]=$'\e[32m'   [lightgreen]=$'\e[92m'
        [yellow]=$'\e[33m'  [lightyellow]=$'\e[93m'
        [blue]=$'\e[34m'    [lightblue]=$'\e[94m'
        [magenta]=$'\e[35m' [lightmagenta]=$'\e[95m'
        [cyan]=$'\e[36m'    [lightcyan]=$'\e[96m'
        # Background
        [bgdefault]=$'\e[49m'
        [bgblack]=$'\e[40m'     [bgwhite]=$'\e[107m'
        [bggray]=$'\e[100m'     [bglightgray]=$'\e[47m'
        [bgred]='\e[41m'        [bglightred]='\e[101m'
        [bggreen]='\e[42m'      [bglightgreen]='\e[102m'
        [bgyellow]=$'\e[43m'    [bglightyellow]=$'\e[103m'
        [bgblue]='\e[44m'       [bglightblue]='\e[104m'
        [bgmagenta]=$'\e[45m'   [bglightmagenta]=$'\e[105m'
        [bgcyan]=$'\e[46m'      [bglightcyan]=$'\e[106m'
    )
    local fmtseq=$''
    local fmtreset="${escapecodes[reset]}"
    # Die Formatangaben parsen
    while (( $# > 0 )); do
        [[ "$1" == "--" ]] && { shift ; break ; }
        local format
        for format in ${1//,/ }; do
            if [[ -z "${escapecodes[${format}]+IsSet}" ]]; then
                echo "${FUNCNAME[0]}: unknown format \"${format}\"" >&2
                return 1
            fi
            fmtseq+="${escapecodes[${format}]}"
        done
        shift
    done
    # Keine Formatierung, falls wir nicht mit einem Terminal verbunden sind
    ${istty:-false} || { fmtseq='' ; fmtreset='' ; }
    # Ohne Textparameter von der Standardeingabe lesen und formatiert ausgeben
    if (( $# == 0 )); then
        local stdin
        while read -r stdin; do
            printf "${fmtseq}%s${fmtreset}\n" "${stdin}"
        done
    fi
    # Die Textparameter formatiert ausgeben
    while (( $# > 0 )); do
        printf "${fmtseq}%s${fmtreset}" "${1}"
        shift
        (( $# > 0 )) && printf " " || printf "\n"
    done
}


# Hilfsfunktion zur Ausgabe der Zeitdauer zwischen zwei UTC-Zeitstempeln im Format HH:MM:SS
# Usage: duration [von] [bis]
duration() {
    local now=$(date '+%s')
    local from=${1-${now}}
    local to=${2-${now}}
    local rt=$(( ${to} - ${from} ))
    printf '%02d:%02d:%02d\n' "$((rt/3600))" "$(((rt%3600)/60))" "$(((rt%3600)%60))"
}


# Hilfsfunktion zum zeilenweise Zerlegen großer Ausgabedateien
# ACHTUNG: "shopt -s extglob" muss aktiviert sein!
# Usage: chop [file] ...
chop() {
    local maxsizemb=50
    local maxbytes=$(( ${maxsizemb} * 1024 * 1024 ))
    local currentfile chopfile chopname chopext chopdir partprefix header maxsize
    while (( $# > 0 )); do
        currentfile=$1
        # Nichts tun wenn die Datei ist kleiner als das Limit ist
        if (( $(wc -c < "${currentfile}") <= ${maxbytes} )); then
            # echo "${currentfile}"
            shift
            continue
        fi
        # Lokal im Verzeichnis in dem die Datei liegt arbeiten
        pushd "$(dirname "${currentfile}")" >/dev/null
        chopfile=$(basename "${currentfile}")
        chopname="${chopfile%.*}"
        chopext="${chopfile##*.}"
        chopdir=$(dirname "${currentfile}")
        [[ "${chopfile}" == "${currentfile}" ]] && chopdir=""
        partprefix="${chopname}."
        # Sicherstellen das die zerlegten Dateien nicht bereits existieren
        if ls "${partprefix}"+([0-9])?(".${chopext}") >/dev/null 2>&1 && ! ${force:-false}; then
            echo "Die Datei \"$(ls -C1 "${partprefix}"+([0-9])?(".${chopext}") | head -n 1)\" existiert bereits" >&2
            popd >/dev/null
            return 99
        fi
        rm -f "${partprefix}"+([0-9])?(".${chopext}") >/dev/null 2>&1 || true
        # Die Datei zerlegen
        header=$(head -n 1 "${chopfile}")
        maxsize=$(( ${maxbytes} - ${#header} - 1 ))
        split -C "${maxsize}" -da 3 "${chopfile}" "${partprefix}"
        # Den Header einfügen und die ursprüngliche Dateiendung wieder anhängen
        local partfile topline filesize records fullname
        for partfile in "${partprefix}"+([0-9]); do
            topline=$(head -n 1 "${partfile}")
            [[ "${topline}" == "${header}" ]] || sed -i "1i${header}" "${partfile}"
            filesize=$(ls -lh "${partfile}" | awk '{print $5}')
            records=$(( $(wc -l < "${partfile}") - 1 ))
            mv -f "${partfile}" "${partfile}.${chopext}"
            fullname="${chopdir:+${chopdir}/}${partfile}.${chopext}"
            echo -e "Teildatei \"${fullname}\" erzeugt  (${records} Records|${filesize})"
        done
        rm -f "${chopfile}"
        popd >/dev/null
        shift
    done
}


# Hilfskonstrukte zum Aufräumen bei Script-Ende definieren und registrieren
declare -a exit_actions=()

on_exit() {
    local cmd=$(printf '"%s" ' "${@}")
    exit_actions+=("${cmd}")
}

eval_exit_actions() {
    local action
    for action in "${exit_actions[@]}"; do
        eval "${action}" || true
    done
}

trap eval_exit_actions EXIT


# Keyboard Interrupts (SIGINT) abfangen und das Script beenden
# Da sich "sqlplus" bei Interrupts normal beendet, bricht das Script ansonsten bei Ctrl+C nicht ab
die_of_sigint() {
    echo -e "\n$(colorize bold,red -- "ABBRUCH: Interrupt via Keyboard erhalten!")" >&2
    trap - INT
    kill -s INT "$$"
}

trap die_of_sigint INT


# Das Environment aufsetzen und prüfen
expstart=$(date '+%s')
haswarnings=false
databaseid="GADB"

: ${ORACLE_HOME:?"Pfad der Oracle-Installation ist nicht gesetzt!"}
# export NLS_LANG='AMERICAN_AMERICA.UTF8'
export NLS_LANG='GERMAN_GERMANY.WE8MSWIN1252'
export NLS_TIMESTAMP_FORMAT='YYYY-MM-DD HH24:MI:SS'
export NLS_DATE_FORMAT='YYYY-MM-DD'

# Die Zugangsdaten für die Oracle-Datenbank parsen
: ${ORAENV:?"Pfad der Oracle-Umgebungskonfiguration (üblicherweise ~/etc/oracle.env) ist nicht gesetzt!"}
dbparams=$(awk --re-interval -F':' -v Id="${databaseid}" '/^(.+:){4}/ {if ($1==Id) {print $0; exit 0;}}' "${ORAENV}")
dbschema=$(echo "${dbparams}" | awk -F':' '{print $2}')
dbpassword=$(echo "${dbparams}" | awk -F':' '{print $3}')
tnsname=$(echo "${dbparams}" | awk -F':' '{print $4}')


# In das Ausgabeverzeichnis wechseln
[[ -e "${outputdir:="."}" ]] || mkdir "${outputdir}"
pushd "${outputdir}" >/dev/null
echo "Ausgabeverzeichnis ist $(pwd)"


# In der Datenbank werden für den CSV-Export einige temporäre Hilfsobjekte angelegt
# Um mehrere Instanzen parallel betreiben zu können, werden die Namen mit einer eindeutigen Session-ID versehen
readonly session_id=$(tr -dc "a-z0-9" < /dev/urandom | head -c 10) || true

# Sicherstellen dass die Objekte automatisch (auch im Fehlerfall) wieder aus der Datenbank entfernt werden
cleanupdb() {
    sqlplus "${dbschema}/${dbpassword}@${tnsname}" >/dev/null 2>&1 <<-END_OF_SQL
                DROP FUNCTION csvify_${session_id};
                DROP TYPE csvdata_${session_id};
        END_OF_SQL
}
on_exit cleanupdb

# Die Hilfsobjekte anlegen
sqlplus -S "${dbschema}/${dbpassword}@${tnsname}" <<END_OF_SQL | { egrep 'Warning|Error|ORA-|SP2-' >&2 || true ; }
        whenever sqlerror exit failure;

        set sqlprompt ''
        set pagesize 0
        set linesize 32767
        set echo off
        set feedback off
        set trimout on
        set termout off
        set heading off
        set verify off

        CREATE OR REPLACE TYPE csvdata_${session_id} AS TABLE OF VARCHAR2(32767);
        /

        CREATE OR REPLACE FUNCTION csvify_${session_id} (sqlquery IN VARCHAR2)
        RETURN csvdata_${session_id} AUTHID CURRENT_USER PIPELINED IS
                cur       NUMBER;
                rec_tab   dbms_sql.desc_tab;
                colcount  INTEGER;
                rowcount  NUMBER;
                data      VARCHAR2(32767);
                header    VARCHAR2(32767);
                rc        NUMBER;
                v_char    VARCHAR2(4000);
                v_num     NUMBER;
                v_date    DATE;
                v_ts      TIMESTAMP;
                sepchar   VARCHAR2(1) := ';';
                quotechar VARCHAR2(1) := '';
                -- Caution: Do not set NULL or empty, else translate returns NULL!
                mapfrom   VARCHAR2(5) := ';';
                mapto     VARCHAR2(5) := ',';
        BEGIN
                -- Build the new query and identify the result columns
                cur := dbms_sql.open_cursor;
                dbms_sql.parse(cur, sqlquery, dbms_sql.native);
                dbms_sql.describe_columns(cur, colcount, rec_tab);
                header := '';
                FOR i IN 1..rec_tab.LAST LOOP
                        header := header || quotechar || rec_tab(i).col_name || quotechar || sepchar;
                        CASE rec_tab(i).col_type
                                WHEN dbms_types.TYPECODE_NUMBER THEN dbms_sql.define_column(cur, i, v_num);
                                WHEN dbms_types.TYPECODE_DATE THEN dbms_sql.define_column(cur, i, v_date);
                                WHEN dbms_types.TYPECODE_TIMESTAMP THEN dbms_sql.define_column(cur, i, v_ts);
                        ELSE
                                dbms_sql.define_column(cur, i, v_char, 4000);
                        END CASE;
                END LOOP;
                -- Output a header line with the column names
                header := substr(header, 1, length(header)-1);
                pipe row(header);
                -- Fetch each row from the result set
                rowcount := dbms_sql.execute(cur);
                LOOP rc := dbms_sql.fetch_rows(cur);
                EXIT WHEN rc = 0;
                        data := '';
                        -- Go through each column and append it to the data line
                        FOR j IN 1 .. rec_tab.COUNT LOOP
                                CASE rec_tab(j).col_type
                                        WHEN dbms_types.TYPECODE_NUMBER THEN
                                                dbms_sql.column_value(cur, j, v_num);
                                                IF trunc(v_num) <> v_num OR rec_tab(j).col_scale > 0 OR
                                                        (rec_tab(j).col_scale = -127 AND rec_tab(j).col_precision > 0) THEN
                                                        data := data || to_char(v_num,
                                                                'FM9999999999999999999999999999990D0999999999999999999999999999999',
                                                                'NLS_NUMERIC_CHARACTERS='',.''') || sepchar;
                                                ELSE
                                                        data := data || to_char(v_num,
                                                                'FM99999999999999999999999999999999999990',
                                                                'NLS_NUMERIC_CHARACTERS='',.''') || sepchar;
                                                END IF;
                                        WHEN dbms_types.TYPECODE_DATE THEN
                                                dbms_sql.column_value(cur, j, v_date);
                                                data := data || to_char(v_date, 'YYYY-MM-DD') || sepchar;
                                        WHEN dbms_types.TYPECODE_TIMESTAMP THEN
                                                dbms_sql.column_value(cur, j, v_ts);
                                                data := data || to_char(v_date, 'YYYY-MM-DD HH24:MI:SS') || sepchar;
                                ELSE
                                        dbms_sql.column_value(cur, j, v_char);
                                        IF v_char IS NULL THEN
                                                data := data || sepchar;
                                        ELSE
                                                data := data || quotechar || translate(v_char, mapfrom, mapto) || quotechar || sepchar;
                                        END IF;
                                END CASE;
                        END LOOP;
                        -- Output the data line
                        data := substr(data, 1, length(data)-1);
                        pipe row(data);
                END LOOP;
        END;
        /

        show error;

        DECLARE
                errorcount INTEGER;
        BEGIN
                SELECT count(*) INTO errorcount
                FROM user_errors
                WHERE lower(name) in ('csvify_${session_id}', 'csvdata_${session_id}');
                IF (errorcount > 0) THEN
                        raise_application_error(-20001, 'Hilfsobjekte konnten nicht angelegt werden');
                END IF;
        END;
        /
END_OF_SQL


# Die zu exportierenden Tabellen und die dafür verwendeten Queries definieren
declare -A QUERIES=(
    [PB_HIS_CONTRACT]='select * from PB_HIS_CONTRACT partition (::PARTITION::) order by CONTRACT_ID'
    [PB_HIS_CONTRACT_PART]='select * from PB_HIS_CONTRACT_PART partition (::PARTITION::) order by CNTRCT_PRT_ID'
    [PB_HIS_INTEREST_PART]='select * from PB_HIS_INTEREST_PART partition (::PARTITION::) order by CONTRACT_PART_ID'
    [PB_HIS_OPTION_PART]='select * from PB_HIS_OPTION_PART partition (::PARTITION::) order by CONTRACT_PART_ID'
    [PB_HIS_PRINCIPAL_PART]='select * from PB_HIS_PRINCIPAL_PART partition (::PARTITION::) order by CONTRACT_PART_ID'
    [PB_HIS_FREE_DEFINED_ATTRIBUTES]='select * from PB_HIS_FREE_DEFINED_ATTRIBUTES partition (::PARTITION::) order by FDA_CONTRACT_ID'
    [PB_REP_REPORTING]='select * from PB_REP_REPORTING partition (::PARTITION::) order by CONTRACT_ID, REPORTING_SOURCE'
    [HY_CONTRACT_HIST_RES]='select * from HY_CONTRACT_HIST_RES partition (::PARTITION::) order by CONTRACTID, BEGINDATE, ROLLUPRUNID'
    [HY_CONTRACTRESULT_ACCSYS]='select * from HY_CONTRACTRESULT_ACCSYS partition (::PARTITION::) order by CONTRACTID, ACCOUNTID'
    [HY_CONTRACTRESULT_FTP]='select * from HY_CONTRACTRESULT_FTP partition (::PARTITION::) order by CONTRACTID, ACCOUNTID'
    [HY_CONTRACTRESULT_MRE]='select * from HY_CONTRACTRESULT_MRE partition (::PARTITION::) order by CONTRACTID, ACCOUNTID, CASHFLOWBASIS'
    [HY_SENSITIVITY_PER_BUCKET]='select * from HY_SENSITIVITY_PER_BUCKET partition (::PARTITION::) order by CONTRACTID, TBS_ID, KIND, FLOW, CASHFLOWBASIS'
    [HY_LIQUIDITY_PER_BUCKET]='select * from HY_LIQUIDITY_PER_BUCKET partition (::PARTITION::) order by CONTRACTID, TBS_ID, KIND, FLOW, CASHFLOWBASIS'
    [HY_ROLLUP_HIST_RES]='select * from HY_ROLLUP_HIST_RES order by BEGINDATE, ROLLUPRUNID'
)


# Pro genanntem Stichtag/Partition alle Tabellen exportieren
for partition in "${PARTITIONS[@]}"; do
    partstart=$(date '+%s')
    # partdate="${partition#T_}" ; partdate=${partdate//_/}
    echo -e "\n$(colorize bold,white,underline -- "Partition \"${partition}\":")"

    for table in "${!QUERIES[@]}"; do
        tabstart=$(date '+%s')
        tabquery="${QUERIES[${table}]}"
        partquery="${tabquery//::PARTITION::/${partition}}"
        # partquery="${tabquery//::PARTITION::/${partition}} fetch first 2500 rows only"

        exportfile="${partition#T_}/${table^^}.csv"
        spoolfile=$(mktemp "sqlspool.XXXXXXXX")
        termfile=$(mktemp "termout.XXXXXXXX")
        # on_exit rm -f "$(readlink -f "${spoolfile}")" "$(readlink -f "${termfile}")"

        printf "Exportiere Tabelle \"${table}\" nach \"${exportfile}\""
        success=false
        sqlplus -S "${dbschema}/${dbpassword}@${tnsname}" <<-END_OF_SQL | { egrep '^Warning|^Error|^ORA-|^SP2-' >"${termfile}" || true ; } && success=true
                        whenever sqlerror exit failure;
                        set sqlprompt ''
                        set serveroutput on
                        set pagesize 0
                        set linesize 32767
                        set trimspool on
                        set trimout on
                        set echo off
                        set auto off
                        set feedback off
                        set heading off
                        set verify off
                        set tab off
                        set flush off
                        set arraysize 5000
                        spool '${spoolfile}'
                        select * from table(csvify_${session_id}('${partquery}'));
                        spool off
                END_OF_SQL

        # Bei Fehlern eine Warnmeldung ausgeben und die weitere Verarbeitung für die Datei überspringen
        if ! ${success:-false} || [[ -s ${termfile} ]]; then
            echo -e "\n$(colorize bold,yellow -- "WARNUNG: Die Daten der Tabelle konnte nicht fehlerfrei exportiert werden!")"
            haswarnings=true
            cat "${termfile}" >&2
            rm -f "${termfile}"
            continue
        fi
        rm -f "${termfile}"

        # Eine Statusmeldung zum Export ausgeben
        runtime=$(duration "${tabstart}")
        filesize=$(ls -lh "${spoolfile}" | awk '{print $5}')
        records=$(( $(wc -l < "${spoolfile}") - 1 ))
        printf "  (${records} Records|${filesize}|${runtime})\n"

        # Die Spool-Dateien auf den finalen Namen verschieben
        if [[ -e ${exportfile} ]] && ! ${force:-false}; then
            echo "$(colorize bold,red -- "ABBRUCH: Die Ausgabedatei \"${exportfile}\" existiert bereits!")" >&2
            exit 10
        fi
        mkdir -p "$(dirname "${exportfile}")"
        mv -f "${spoolfile}" "${exportfile}"
        ${sqlinfo:-false} && echo "${partquery}" >"${exportfile%.*}.sql"

        # Warnmeldung wenn die maximale Zeilenlänge an das Limit von sqlplus reicht
        if (( $(wc -L < "${exportfile}") >= 32767 )); then
            echo "$(colorize bold,yellow -- "WARNUNG: Maximale Zeilenlänge erreicht! Möglicherweise wurden Zeilen abgeschnitten.")"
            haswarnings=true
        fi

        # Große Export-Dateien in mehrere kleine Teile zerlegen
        chop "${exportfile}"
    done

    echo "Partitionsdaten in $(duration "${partstart}") exportiert!"
done


if ${haswarnings:-false}; then
    echo -e "\n$(colorize bold,red -- "Export in $(duration "${expstart}") mit Warnungen beendet!")"
else
    echo -e "\n$(colorize bold,green -- "Export in $(duration "${expstart}") erfolgreich beendet!")"
fi
popd >/dev/null
