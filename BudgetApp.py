from datetime import datetime
import re
import pandas as pd
import requests
import streamlit as st

# --- НАСТРОЙКИ ---
SCRIPT_URL = st.secrets.get("SCRIPT_URL", "")

DATA_WORKSHEET = "БД"
DICT_WORKSHEET = "Спр_Категории"
TOTAL_EXP_WORKSHEET = "Общий расход"

FAMILY_MEMBERS = ["Катя", "Артем", "Маша", "Алиса"]
SHARED_LABEL = "Неопр... (на всех)"
FORM_USERS = FAMILY_MEMBERS + [SHARED_LABEL]

st.set_page_config(page_title="Семейный бюджет", page_icon="👨‍👩‍👧‍👦", layout="wide")
# --- ЗАЩИТА ПАРОЛЕМ ---
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.title("🔒 Вход в семейный бюджет")
    pwd = st.text_input("Введите пароль доступа:", type="password")
    if st.button("Войти", type="primary"):
        if pwd == st.secrets.get("APP_PASSWORD", ""):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Неверный пароль!")
    st.stop()  # Останавливает загрузку всего остального кода до ввода пароля


def get_item(seq, idx, default=""):
    try:
        return seq[idx]
    except (IndexError, TypeError):
        return default


def fix_layout(text):
    if not text:
        return ""
    lat = "qwertyuiop[]asdfghjkl;'zxcvbnm,.`QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>~"
    cyr = "йцукенгшщзхъфывапролджэячсмитьбюёЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮЁ"
    return text.translate(str.maketrans(lat, cyr))


def to_lat_layout(text):
    if not text:
        return ""
    lat = "qwertyuiop[]asdfghjkl;'zxcvbnm,.`QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>~"
    cyr = "йцукенгшщзхъфывапролджэячсмитьбюёЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮЁ"
    return text.translate(str.maketrans(cyr, lat))


def clean_currency(val):
    if isinstance(val, (int, float)):
        return float(val)
    cleaned = re.sub(r"[^\d.,-]", "", str(val)).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


@st.cache_data(ttl=300)
def load_categories_dict():
    try:
        resp = requests.get(f"{SCRIPT_URL}?sheet={DICT_WORKSHEET}", timeout=15)
        rows = resp.json()
        cat_map = {}
        for row in rows[1:]:
            raw_name = str(get_item(row, 0, "")).strip()
            if raw_name:
                raw_desc = str(get_item(row, 1, "")).strip()
                raw_type = str(get_item(row, 2, "Персональная")).strip()
                cat_map[raw_name] = {"desc": raw_desc, "type": raw_type}
        sorted_keys = sorted(cat_map.keys(), key=lambda k: k.lower())
        return {k: cat_map[k] for k in sorted_keys}
    except Exception as e:
        st.error(f"Ошибка загрузки категорий: {e}")
        return {"Прочее": {"desc": "", "type": "Персональная"}}
# --- КОНЕЦ БЛОКА 1 ---
@st.cache_data(ttl=60)
def load_data():
    try:
        resp = requests.get(f"{SCRIPT_URL}?sheet={DATA_WORKSHEET}", timeout=15)
        raw_values = resp.json()
    except Exception as e:
        st.error(f"Ошибка загрузки БД: {e}")
        return pd.DataFrame()

    if not raw_values or len(raw_values) < 2:
        return pd.DataFrame()

    trimmed_rows = []
    for sheet_row_idx, r in enumerate(raw_values[1:], start=2):
        row_5 = [get_item(r, i, "") for i in range(5)] + [sheet_row_idx]
        trimmed_rows.append(row_5)

    df = pd.DataFrame(
        trimmed_rows,
        columns=[
            "Дата",
            "Категория",
            "Имя",
            "Сумма",
            "Примечание",
            "row_idx",
        ],
    )
    df = df[df["Дата"].str.strip() != ""]
    df["Дата"] = pd.to_datetime(df["Дата"], format="%d.%m.%Y", errors="coerce")
    df = df.dropna(subset=["Дата"])

    df["Сумма"] = df["Сумма"].apply(clean_currency)
    df["Категория"] = df["Категория"].str.strip()
    df["Имя"] = df["Имя"].str.strip()
    df["Примечание"] = df["Примечание"].fillna("").str.strip()
    return df


@st.cache_data(ttl=60)
def load_total_expenses():
    try:
        resp = requests.get(
            f"{SCRIPT_URL}?sheet={TOTAL_EXP_WORKSHEET}", timeout=15
        )
        raw_values = resp.json()
    except Exception:
        return pd.DataFrame()

    if not raw_values or len(raw_values) < 2:
        return pd.DataFrame()

    rows = []
    for sheet_row_idx, r in enumerate(raw_values[1:], start=2):
        d_str = str(get_item(r, 0, "")).strip()
        s_val = clean_currency(get_item(r, 1, 0))
        if d_str:
            rows.append([d_str, s_val, sheet_row_idx])

    df_tot = pd.DataFrame(rows, columns=["Дата_стр", "Сумма", "row_idx"])
    df_tot["Дата"] = pd.to_datetime(
        df_tot["Дата_стр"], format="%d.%m.%Y", errors="coerce"
    )
    df_tot = df_tot.dropna(subset=["Дата"])
    df_tot["Год"] = df_tot["Дата"].dt.year
    df_tot["Месяц"] = df_tot["Дата"].dt.month
    return df_tot


# --- ШАПКА ИНТЕРФЕЙСА ---
col_title, col_refresh = st.columns((4, 1))
with col_title:
    st.title("👨‍👩‍👧‍👦 Семейный бюджет")
with col_refresh:
    st.write("")
    if st.button("🔄 Обновить данные", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

categories_dict = load_categories_dict()
all_categories = list(categories_dict.keys())

tab_add, tab_total, tab_report = st.tabs(
    ["➕ Добавить расход", "💳 Общий расход", "📊 Авто-свод и поиск"]
)
# --- КОНЕЦ БЛОКА 2 ---
# === ВКЛАДКА 1: ВНЕСЕНИЕ ДАННЫХ ===
with tab_add:
    if "who_widget" not in st.session_state:
        st.session_state["who_widget"] = []
    if "last_cat_display" not in st.session_state:
        st.session_state["last_cat_display"] = None

    def format_cat_option(cat_name):
        lat_hint = to_lat_layout(cat_name.lower())
        return f"{cat_name}  ({lat_hint})"

    c1, c2 = st.columns(2)
    with c1:
        selected_cat = st.selectbox(
            "Категория (начните вводить на русском или латинице)",
            options=all_categories,
            index=None,
            format_func=format_cat_option,
            placeholder="Выберите категорию...",
        )

        if selected_cat != st.session_state["last_cat_display"]:
            st.session_state["last_cat_display"] = selected_cat
            if selected_cat and selected_cat in categories_dict:
                cat_type = categories_dict[selected_cat]["type"].lower()
                if cat_type == "общая":
                    st.session_state["who_widget"] = [SHARED_LABEL]
                else:
                    st.session_state["who_widget"] = []

        if selected_cat and selected_cat in categories_dict:
            info_desc = categories_dict[selected_cat]["desc"]
            info_type = categories_dict[selected_cat]["type"]
            hint_text = f"Тип: **{info_type}**" + (
                f" — {info_desc}" if info_desc else ""
            )
            st.info(f"💡 {hint_text}")

        who_selected = st.multiselect(
            "На кого записать",
            options=FORM_USERS,
            key="who_widget",
            placeholder="Выберите 1, 2, 3 или всех...",
        )

    with c2:
        date_val = st.date_input("Дата", datetime.today())
        op_type = st.radio(
            "Тип операции", ["Расход (+)", "Возврат / Минус (-)"], horizontal=True
        )
        amount_val = st.number_input("Общая сумма (₽)", min_value=1.0, step=100.0)
        note_val = st.text_input("Примечание (необязательно)")

    if st.button(
        "💾 Записать в БД", type="primary", use_container_width=True
    ):
        if not selected_cat:
            st.error("Выберите категорию!")
        elif not who_selected:
            st.error("Выберите хотя бы одного человека!")
        else:
            target_people = (
                FAMILY_MEMBERS.copy()
                if SHARED_LABEL in who_selected
                else who_selected
            )
            total_amount = (
                -amount_val if op_type == "Возврат / Минус (-)" else amount_val
            )
            count = len(target_people)
            split_amount = round(total_amount / count, 2)

            rows_to_insert = []
            for idx, person in enumerate(target_people):
                person_amount = (
                    round(total_amount - split_amount * (count - 1), 2)
                    if idx == count - 1
                    else split_amount
                )
                final_note = note_val
                if count > 1:
                    tag = (
                        "[Общее 1/4]"
                        if count == 4
                        else f"[1/{count} от {abs(total_amount):g} ₽]"
                    )
                    final_note = f"{note_val} {tag}".strip() if note_val else tag
                rows_to_insert.append([
                    date_val.strftime("%d.%m.%Y"),
                    selected_cat,
                    person,
                    person_amount,
                    final_note,
                ])

            try:
                payload = {
                    "action": "append",
                    "sheet": DATA_WORKSHEET,
                    "rows": rows_to_insert,
                }
                resp = requests.post(SCRIPT_URL, json=payload, timeout=15)
                if resp.status_code == 200:
                    st.cache_data.clear()
                    st.success(
                        f"✅ Записано: **{selected_cat}** | **{total_amount:,.2f} ₽** ({', '.join(target_people)})"
                    )
                else:
                    st.error(f"Ошибка записи: {resp.text}")
            except Exception as e:
                st.error(f"Не удалось отправить данные: {e}")
# --- КОНЕЦ БЛОКА 3 ---
# === ВКЛАДКА 2: ОБЩИЙ РАСХОД (ДЛЯ РАСЧЕТА КАТЕГОРИИ ПРОДУКТЫ) ===
with tab_total:
    st.subheader("💳 Учет общих трат за месяц (база для расчета «Продуктов»)")
    df_tot = load_total_expenses()

    today_dt = datetime.today()
    cur_year, cur_month = today_dt.year, today_dt.month
    today_str = today_dt.strftime("%d.%m.%Y")

    existing_row = pd.DataFrame()
    if not df_tot.empty:
        existing_row = df_tot[
            (df_tot["Год"] == cur_year) & (df_tot["Месяц"] == cur_month)
        ]

    if not existing_row.empty:
        first_rec = get_item(existing_row.to_dict(orient="records"), 0, {})
        last_date_str = first_rec.get("Дата_стр", "")
        current_saved_sum = first_rec.get("Сумма", 0.0)
        target_row_idx = int(first_rec.get("row_idx", 2))
        st.info(
            f"📅 Дата последнего внесения за текущий месяц ({cur_month:02d}.{cur_year}): **{last_date_str}** (сохраненная сумма: **{current_saved_sum:,.2f} ₽**)"
        )
    else:
        target_row_idx = None
        st.info(
            f"📅 За текущий месяц ({cur_month:02d}.{cur_year}) записей еще нет. Создастся новая строка с датой **{today_str}**."
        )

    new_total_sum = st.number_input(
        "Введите актуальную общую сумму расходов за месяц (₽)",
        min_value=0.0,
        value=None,
        step=500.0,
        placeholder="Введите сумму...",
    )

    if st.button("🔄 Обновить БД", type="primary"):
        if new_total_sum is None:
            st.error("Введите сумму перед обновлением!")
        else:
            try:
                if target_row_idx is not None:
                    payload = {
                        "action": "update",
                        "sheet": TOTAL_EXP_WORKSHEET,
                        "row_idx": target_row_idx,
                        "row": [today_str, new_total_sum],
                    }
                else:
                    payload = {
                        "action": "append",
                        "sheet": TOTAL_EXP_WORKSHEET,
                        "rows": [[today_str, new_total_sum]],
                    }
                resp = requests.post(SCRIPT_URL, json=payload, timeout=15)
                if resp.status_code == 200:
                    st.cache_data.clear()
                    st.success(
                        f"✅ Лист «{TOTAL_EXP_WORKSHEET}» обновлен! Дата: **{today_str}**, Сумма: **{new_total_sum:,.2f} ₽**"
                    )
                    st.rerun()
                else:
                    st.error(f"Ошибка сервера: {resp.text}")
            except Exception as e:
                st.error(f"Ошибка соединения: {e}")

    if not df_tot.empty:
        st.divider()
        st.caption("История по месяцам (лист «Общий расход»):")
        hist_df = df_tot.sort_values(by="Дата", ascending=False)[
            ["Дата_стр", "Сумма"]
        ].rename(columns={"Дата_стр": "Дата обновления", "Сумма": "Сумма (₽)"})
        st.dataframe(
            hist_df.style.format({"Сумма (₽)": "{:,.2f} ₽"}),
            hide_index=True,
            use_container_width=True,
        )
# --- КОНЕЦ БЛОКА 4 ---
# === ВКЛАДКА 3: АВТО-СВОД, ПОИСК, РЕДАКТИРОВАНИЕ И УДАЛЕНИЕ ===
with tab_report:
    df = load_data()
    df_tot = load_total_expenses()

    if df.empty and df_tot.empty:
        st.warning("Пока нет данных для формирования свода.")
    else:
        years_set = set()
        if not df.empty:
            df["Год"] = df["Дата"].dt.year
            df["Месяц"] = df["Дата"].dt.month
            years_set.update(df["Год"].unique())
        if not df_tot.empty:
            years_set.update(df_tot["Год"].unique())

        f1, f2 = st.columns(2)
        with f1:
            mode = st.radio(
                "Период свода", ["За месяц", "За год"], horizontal=True
            )
        with f2:
            sel_year = st.selectbox(
                "Выберите год", sorted(list(years_set), reverse=True)
            )

        if mode == "За месяц":
            months = {
                1: "Январь",
                2: "Февраль",
                3: "Март",
                4: "Апрель",
                5: "Май",
                6: "Июнь",
                7: "Июль",
                8: "Август",
                9: "Сентябрь",
                10: "Октябрь",
                11: "Ноябрь",
                12: "Декабрь",
            }
            avail_m = set()
            if not df.empty:
                avail_m.update(df[df["Год"] == sel_year]["Месяц"].unique())
            if not df_tot.empty:
                avail_m.update(
                    df_tot[df_tot["Год"] == sel_year]["Месяц"].unique()
                )
            sel_month = st.selectbox(
                "Выберите месяц",
                sorted(list(avail_m), reverse=True),
                format_func=lambda x: months[x],
            )
            period_df = (
                df[(df["Год"] == sel_year) & (df["Месяц"] == sel_month)].copy()
                if not df.empty
                else pd.DataFrame()
            )
            period_tot_sum = (
                df_tot[
                    (df_tot["Год"] == sel_year) & (df_tot["Месяц"] == sel_month)
                ]["Сумма"].sum()
                if not df_tot.empty
                else 0.0
            )
        else:
            period_df = (
                df[df["Год"] == sel_year].copy()
                if not df.empty
                else pd.DataFrame()
            )
            period_tot_sum = (
                df_tot[df_tot["Год"] == sel_year]["Сумма"].sum()
                if not df_tot.empty
                else 0.0
            )

        recorded_sum = (
            period_df[period_df["Категория"].str.lower() != "продукты"][
                "Сумма"
            ].sum()
            if not period_df.empty
            else 0.0
        )
        products_calc_sum = max(0.0, period_tot_sum - recorded_sum)

        expanded_rows = []
        if not period_df.empty:
            for _, row in period_df.iterrows():
                if row["Категория"].lower() == "продукты":
                    continue
                if row["Имя"].lower().startswith("неопр"):
                    share = row["Сумма"] / len(FAMILY_MEMBERS)
                    for member in FAMILY_MEMBERS:
                        expanded_rows.append({
                            "Категория": row["Категория"],
                            "Имя": member,
                            "Сумма": share,
                        })
                else:
                    expanded_rows.append({
                        "Категория": row["Категория"],
                        "Имя": row["Имя"],
                        "Сумма": row["Сумма"],
                    })

        prod_share = products_calc_sum / len(FAMILY_MEMBERS)
        for member in FAMILY_MEMBERS:
            expanded_rows.append({
                "Категория": "Продукты",
                "Имя": member,
                "Сумма": prod_share,
            })

        st.subheader("1. Сводная таблица")
        st.caption(
            f"Общий расход: **{period_tot_sum:,.0f} ₽** | Внесено по категориям: **{recorded_sum:,.0f} ₽** | Расчетные «Продукты»: **{products_calc_sum:,.0f} ₽**"
        )

        pivot = pd.pivot_table(
            pd.DataFrame(expanded_rows),
            values="Сумма",
            index="Категория",
            columns="Имя",
            aggfunc="sum",
            fill_value=0,
        )
        for u in FAMILY_MEMBERS:
            if u not in pivot.columns:
                pivot[u] = 0.0
        pivot = pivot[FAMILY_MEMBERS].sort_index(key=lambda x: x.str.lower())
        pivot.insert(0, "Итого", pivot.sum(axis=1))
        pivot.loc["ВСЕГО"] = pivot.sum()
        st.dataframe(
            pivot.style.format("{:,.0f} ₽"),
            use_container_width=True,
            height=550,
        )
# --- КОНЕЦ БЛОКА 5 ---
        st.divider()
        st.subheader("2. Детализация, поиск, редактирование и удаление трат")
        if period_df.empty:
            st.info("За выбранный период нет отдельных записей в БД.")
        else:
            d1, d2, d3 = st.columns(3)
            with d1:
                filter_who = st.multiselect(
                    "Фильтр по человеку",
                    options=sorted(period_df["Имя"].unique()),
                    placeholder="Все",
                )
            with d2:
                filter_cat = st.multiselect(
                    "Фильтр по категории",
                    options=sorted(period_df["Категория"].unique()),
                    placeholder="Все категории",
                )
            with d3:
                search_text = st.text_input(
                    "Поиск по примечанию (латиница/рус)",
                    placeholder="бассейн или ,fcctqy...",
                )

            details_df = period_df.copy()
            if filter_who:
                details_df = details_df[details_df["Имя"].isin(filter_who)]
            if filter_cat:
                details_df = details_df[details_df["Категория"].isin(filter_cat)]
            if search_text:
                fixed_search = fix_layout(search_text)
                m1 = details_df["Примечание"].str.contains(
                    search_text, case=False, na=False, regex=False
                )
                m2 = details_df["Примечание"].str.contains(
                    fixed_search, case=False, na=False, regex=False
                )
                details_df = details_df[m1 | m2]

            details_df = details_df.sort_values(
                by=["Дата", "row_idx"], ascending=[False, False]
            )
            details_df["Дата_стр"] = details_df["Дата"].dt.strftime("%d.%m.%Y")
            st.markdown(
                f"**Найдено записей:** {len(details_df)} | **Сумма:** `{details_df['Сумма'].sum():,.2f} ₽`"
            )

            if "edit_row_id" not in st.session_state:
                st.session_state["edit_row_id"] = None

            col_widths = (1.2, 1.8, 1.2, 1.3, 2.5, 1.2)
            hc_date, hc_cat, hc_who, hc_sum, hc_note, hc_act = st.columns(
                col_widths
            )
            hc_date.markdown("**Дата**")
            hc_cat.markdown("**Категория**")
            hc_who.markdown("**Имя**")
            hc_sum.markdown("**Сумма**")
            hc_note.markdown("**Примечание**")
            hc_act.markdown("**Действия**")
            st.markdown(
                "<hr style='margin: 4px 0 8px 0;'>", unsafe_allow_html=True
            )
# --- КОНЕЦ БЛОКА 6 ---
            for rec in details_df.to_dict(orient="records"):
                r_id = int(rec["row_idx"])
                rc_date, rc_cat, rc_who, rc_sum, rc_note, rc_act = st.columns(
                    col_widths
                )
                rc_date.write(rec["Дата_стр"])
                rc_cat.write(rec["Категория"])
                rc_who.write(rec["Имя"])
                rc_sum.write(f"{rec['Сумма']:,.2f} ₽")
                rc_note.write(rec["Примечание"] if rec["Примечание"] else "—")

                btn_c1, btn_c2 = rc_act.columns(2)
                with btn_c1:
                    if st.button("✏️", key=f"btn_ed_{r_id}", help="Изменить"):
                        st.session_state["edit_row_id"] = (
                            None
                            if st.session_state["edit_row_id"] == r_id
                            else r_id
                        )
                        st.rerun()
                with btn_c2:
                    if st.button("🗑️", key=f"btn_del_{r_id}", help="Удалить"):
                        requests.post(
                            SCRIPT_URL,
                            json={
                                "action": "delete",
                                "sheet": DATA_WORKSHEET,
                                "row_idx": r_id,
                            },
                            timeout=15,
                        )
                        if st.session_state["edit_row_id"] == r_id:
                            st.session_state["edit_row_id"] = None
                        st.cache_data.clear()
                        st.rerun()

                if st.session_state["edit_row_id"] == r_id:
                    with st.container(border=True):
                        ec1, ec2, ec3 = st.columns(3)
                        with ec1:
                            edit_date = st.date_input(
                                "Дата",
                                value=rec["Дата"].date(),
                                key=f"ed_d_{r_id}",
                            )
                            edit_cat = st.selectbox(
                                "Категория",
                                options=all_categories,
                                index=all_categories.index(rec["Категория"])
                                if rec["Категория"] in all_categories
                                else 0,
                                key=f"ed_c_{r_id}",
                            )
                        with ec2:
                            all_names = FAMILY_MEMBERS + ["Неопр..."]
                            edit_who = st.selectbox(
                                "Имя",
                                options=all_names,
                                index=all_names.index(rec["Имя"])
                                if rec["Имя"] in all_names
                                else 0,
                                key=f"ed_w_{r_id}",
                            )
                            edit_sum = st.number_input(
                                "Сумма (₽)",
                                value=float(rec["Сумма"]),
                                step=100.0,
                                key=f"ed_s_{r_id}",
                            )
                        with ec3:
                            edit_note = st.text_input(
                                "Примечание",
                                value=rec["Примечание"],
                                key=f"ed_n_{r_id}",
                            )

                        b_save, b_cancel = st.columns(2)
                        with b_save:
                            if st.button(
                                "💾 Сохранить изменения",
                                key=f"sv_{r_id}",
                                type="primary",
                                use_container_width=True,
                            ):
                                requests.post(
                                    SCRIPT_URL,
                                    json={
                                        "action": "update",
                                        "sheet": DATA_WORKSHEET,
                                        "row_idx": r_id,
                                        "row": [
                                            edit_date.strftime("%d.%m.%Y"),
                                            edit_cat,
                                            edit_who,
                                            edit_sum,
                                            edit_note,
                                        ],
                                    },
                                    timeout=15,
                                )
                                st.session_state["edit_row_id"] = None
                                st.cache_data.clear()
                                st.rerun()
                        with b_cancel:
                            if st.button(
                                "Отмена",
                                key=f"cn_{r_id}",
                                use_container_width=True,
                            ):
                                st.session_state["edit_row_id"] = None
                                st.rerun()
# --- КОНЕЦ БЛОКА 7 ---
