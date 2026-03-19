import os
import json
import re
import shutil  # <-- Модуль для копирования
from typing import Dict, List, Tuple, Union, Optional, Any # Импортируем нужные типы

def log_verdict(filename: str, verdict: str, reason: str = "", kbks: Optional[List[str]] = None) -> None:
    """Выводит краткий вердикт по файлу."""
    kbks_str = ", ".join(kbks) if kbks else "N/A"
    print(f"[VERDICT] {filename}: {verdict}. KBK Codes: [{kbks_str}]. {reason}".strip())


def find_accept_info_lists_recursive(obj: Any) -> List[Dict[str, Any]]:
    """
    Рекурсивно ищет все вхождения 'AcceptInfoList' в JSON-объекте (dict/list).
    Возвращает список найденных 'AcceptInfoList'.
    """
    results: List[Dict[str, Any]] = []

    def _search(current: Any) -> None:
        if isinstance(current, dict):
            for key, value in current.items():
                if key == "AcceptInfoList":
                    results.append(value)
                else:
                    _search(value)
        elif isinstance(current, list):
            for item in current:
                _search(item)

    _search(obj)
    return results


def load_json_data(json_dir: str) -> Tuple[Dict[str, List[float]], Dict[str, List[float]]]:
    """
    Загружает все JSON-файлы из директории и строит ДВЕ мапы:
    1. subsidies_for_results_map: ИДЕНТИФИКАТОР -> [суммы] для "Объем Субсидии, направленной на достижение результатов".
    2. subsidies_for_return_map: ИДЕНТИФИКАТОР -> [суммы] для "Объем Субсидии, подлежащей возврату в бюджет".
    Использует FederalBudgetCode (без пробелов, последние 2 символа отброшены) как ключ.
    Поиск AcceptInfoList производится рекурсивно по всей структуре.
    """
    subsidies_for_results_map: Dict[str, List[float]] = {}
    subsidies_for_return_map: Dict[str, List[float]] = {}

    for filename in os.listdir(json_dir):
        if not filename.lower().endswith('.json'):
            continue
        path = os.path.join(json_dir, filename)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data_list = json.load(f)
        except json.JSONDecodeError:
            log_verdict(filename, "FAILED TO LOAD", "Invalid JSON format.", [])
            continue
        except FileNotFoundError:
            log_verdict(filename, "FAILED TO LOAD", "File not found.", [])
            continue

        if not isinstance(data_list, list):
            log_verdict(filename, "FAILED TO LOAD", "Root element is not an array.", [])
            continue

        found_items_count_results = 0
        found_items_count_return = 0

        for obj in data_list:
            accept_info_lists = find_accept_info_lists_recursive(obj)

            for accept_info_list in accept_info_lists:
                if isinstance(accept_info_list, dict) and accept_info_list.get('success'):
                    for item in accept_info_list.get('data', []):
                        federal_code_raw = item.get("FederalBudgetCode", "")
                        amount = item.get("AmountSinceFinancialYear", 0)
                        indicator_name = item.get("IndicatorName", "")

                        if federal_code_raw:
                            federal_code_clean = re.sub(r'\s+', '', federal_code_raw)
                            if len(federal_code_clean) >= 2:
                                federal_code_key = federal_code_clean[:-2]

                                if indicator_name == "Объем Субсидии, направленной на достижение результатов":
                                    if federal_code_key not in subsidies_for_results_map:
                                        subsidies_for_results_map[federal_code_key] = []
                                    subsidies_for_results_map[federal_code_key].append(float(amount))
                                    found_items_count_results += 1
                                    # print(f"[DEBUG] Добавлена сумма {amount} для ключа {federal_code_key} (направленной на результаты).")

                                elif indicator_name == "Объем Субсидии, подлежащей возврату в бюджет":
                                    if federal_code_key not in subsidies_for_return_map:
                                        subsidies_for_return_map[federal_code_key] = []
                                    subsidies_for_return_map[federal_code_key].append(float(amount))
                                    found_items_count_return += 1
                                    # print(f"[DEBUG] Добавлена сумма {amount} для ключа {federal_code_key} (подлежащей возврату).")

    # print(f"[DEBUG] Загрузка JSON завершена.")
    # print(f"[DEBUG] Всего уникальных ключей в subsidies_for_results_map: {len(subsidies_for_results_map)}")
    # print(f"[DEBUG] Всего уникальных ключей в subsidies_for_return_map: {len(subsidies_for_return_map)}")
    return subsidies_for_results_map, subsidies_for_return_map


def parse_txt_file(filepath: str) -> List[List[str]]:
    encodings = ['utf-8', 'cp1251']
    lines: List[List[str]] = []
    for enc in encodings:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if line:
                        parts = line.split('|')
                        lines.append(parts)
            break # Успешно прочитали, выходим из цикла
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"Failed to decode file using attempted encodings: {encodings}")
    return lines


def extract_kbks_from_lines(lines: List[List[str]]) -> List[str]:
    """Извлекает уникальные КБК коды (идентификаторы) из строк 500-11 и 500-21."""
    kbks = set()
    for row in lines:
        if len(row) < 9:
            continue
        code = row[0].strip()
        if code in ('500-11', '500-21'):
            identifier = "075" + row[2].strip()
            kbks.add(identifier)
    return sorted(list(kbks))


def validate_txt_file(lines: List[List[str]], subsidies_for_results_map: Dict[str, List[float]], subsidies_for_return_map: Dict[str, List[float]]) -> Tuple[bool, str]:
    total_sum = 0.0
    max_limit: Optional[float] = None

    # --- Определение типа файла (ГЗ или нет) НА ОСНОВЕ любого КБК в 500-11/21 ---
    # Пройдём по всем строкам, чтобы найти КБК 07503
    is_gz_file_internal = False
    for temp_row in lines:
         if len(temp_row) < 9:
             continue
         temp_code = temp_row[0].strip()
         if temp_code in ('500-11', '500-21'):
             temp_identifier = "075" + temp_row[2].strip()
             if temp_identifier.startswith('07503'):
                 is_gz_file_internal = True
                 break

    # print(f"[DEBUG] Файл: is_gz_file_internal: {is_gz_file_internal}")

    # --- Основной цикл проверки ---
    for i, row in enumerate(lines):
        if len(row) < 9:
            continue
        code = row[0].strip()
        if not code.startswith('500-') and code != '500':
            # Проверка других 500-* (не 11 и не 21)
            if code.startswith('500-') and code not in ('500-11', '500-21'):
                 if not is_gz_file_internal: # Только если файл НЕ ГЗ
                     amount_str = row[6].strip()
                     if amount_str == '' or amount_str == '0' or amount_str == '0.00':
                         amount_check = 0.0
                     else:
                         try:
                             amount_check = float(amount_str)
                         except ValueError:
                             return False, f"Invalid number in row {i+1}: '{amount_str}'"
                     if amount_check != 0:
                         return False, f"Non-zero amount ({amount_check}) for code {code} which is not 500-11/21 in non-GZ file."
                 # Если файл ГЗ, просто игнорируем другие 500-* коды в этой проверке
            continue # Продолжаем цикл для строк 500-11, 500-21, 500

        amount_str = row[6].strip()
        if amount_str == '' or amount_str == '0' or amount_str == '0.00':
            amount = 0.0
        else:
            try:
                amount = float(amount_str)
            except ValueError:
                return False, f"Invalid number in row {i+1}: '{amount_str}'"

        if amount < 0:
            return False, f"Negative amount ({amount}) in row {i+1}"

        if code.startswith('500-'):
            if code == '500-11':
                identifier = "075" + row[2].strip()
                # Проверка по subsidies_for_results_map ВСЕГДА происходит
                if identifier not in subsidies_for_results_map or amount not in subsidies_for_results_map[identifier]:
                    return False, f"No matching identifier {identifier} and amount {amount} for 500-11 in JSON (results map)."
                # Суммируем для проверки лимита ТОЛЬКО если файл НЕ ГЗ
                if not is_gz_file_internal:
                    total_sum += amount
            elif code == '500-21':
                recipient_identifier = "075" + row[2].strip()
                recipient_kbk_check = row[4].strip()
                if recipient_kbk_check.endswith('610'):
                    # Проверка по subsidies_for_return_map ВСЕГДА происходит
                    if recipient_identifier not in subsidies_for_return_map or amount not in subsidies_for_return_map[recipient_identifier]:
                        return False, f"No matching identifier {recipient_identifier} and amount {amount} for 500-21 (610) in JSON (return map)."
                    # Суммируем для проверки лимита ТОЛЬКО если файл НЕ ГЗ
                    if not is_gz_file_internal:
                        total_sum += amount
                elif recipient_kbk_check.endswith('150'):
                    # Не проверяем сумму в JSON, просто суммируем для лимита, если НЕ ГЗ
                    if not is_gz_file_internal:
                        total_sum += amount
                else:
                    return False, f"Invalid KBK ending for 500-21: {recipient_kbk_check} (expected 610 or 150)"
            # Этот блок unreachable, так как мы continue выше для других 500-*
            # Но на всякий случай, если логика изменится:
            # if not is_gz_file_internal: # Условие внутри unreachable блока не имеет смысла
            #     if amount != 0: # Это также unreachable
            #         return False, f"Non-zero amount ({amount}) for code {code} which is not 500-1 in non-GZ file."
        elif code == '500':
            # Устанавливаем лимит ТОЛЬКО если файл НЕ ГЗ
            if not is_gz_file_internal:
                max_limit = amount

    # Проверка превышения лимита ТОЛЬКО если файл НЕ ГЗ
    if not is_gz_file_internal:
        if max_limit is not None and total_sum > max_limit:
            return False, f"Total sum ({total_sum}) exceeds limit ({max_limit}) in non-GZ file."

    # Возвращаем True, если не было других ошибок (отрицательные суммы, невалидные числа).
    # Проверки для ГЗ файлов (если is_gz_file_internal) уже пройдены (только 500-11/21 проверены с JSON, лимит и другие 500-XX проигнорированы).
    # Проверки для не-ГЗ файлов тоже пройдены.
    return True, ""


def main() -> None:
    txt_dir = "TXT Outputs"
    json_dir = "Json Outputs"
    correct_dir = "Correct Outputs"
    incorrect_dir = "Incorrect Outputs"

    os.makedirs(correct_dir, exist_ok=True)
    os.makedirs(incorrect_dir, exist_ok=True)

    # Загружаем обе мапы
    subsidies_for_results, subsidies_for_return = load_json_data(json_dir)

    # Проверяем, пусты ли обе мапы
    if not subsidies_for_results and not subsidies_for_return:
        print("[WARNING] Обе мапы с данными из JSON пусты. Проверьте структуру файлов и содержимое AcceptInfoList.data.")
        return # Можно и не возвращаться, если хочется попробовать обработать файлы, даже если мапы пусты

    print(f"[INFO] Загружено {len(subsidies_for_results)} ключей для 'направленной на результаты'.")
    print(f"[INFO] Загружено {len(subsidies_for_return)} ключей для 'подлежащей возврату'.")

    for filename in os.listdir(txt_dir):
        if not filename.lower().endswith('.txt'):
            continue
        filepath = os.path.join(txt_dir, filename)
        try:
            lines = parse_txt_file(filepath)
        except ValueError as e:
            log_verdict(filename, "FAILED TO PARSE", str(e), [])
            continue

        kbks_in_file = extract_kbks_from_lines(lines)
        # Передаём обе мапы в validate_txt_file
        is_valid, reason = validate_txt_file(lines, subsidies_for_results, subsidies_for_return)

        dest_dir = correct_dir if is_valid else incorrect_dir
        dest_path = os.path.join(dest_dir, filename)
        shutil.copy2(filepath, dest_path)

        verdict = "PASSED" if is_valid else "FAILED"
        log_verdict(filename, verdict, reason, kbks_in_file)


if __name__ == "__main__":
    main()