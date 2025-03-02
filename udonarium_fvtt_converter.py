import argparse
import json
import logging
import os
import sys
from lxml import etree

# ロギングの設定
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def get_text(elem):
    """要素からテキストを安全に取得します。"""
    return elem.text.strip() if elem is not None and elem.text else ""

def get_int_value(elem, attrib_name="text"):
    """要素から整数値を安全に取得します。"""
    if elem is None:
        return 0
    value = elem.get(attrib_name) if attrib_name != "text" else elem.text
    try:
        return int(value.strip()) if value else 0
    except (ValueError, AttributeError):
        return 0

def parse_abilities(root, json_data):
    """能力値をXMLからJSONにマッピングします。"""
    ability_mapping = {
        "筋力": "str",
        "敏捷力": "dex",
        "耐久力": "con",
        "知力": "int",
        "判断力": "wis",
        "魅力": "cha",
    }
    for ability_elem in root.findall(".//data[@name='能力値']/data"):
        ability_name_jp = ability_elem.get("name", "").replace("【", "").replace("】", "")
        ability_name_en = ability_mapping.get(ability_name_jp)
        if ability_name_en:
            json_data["system"]["abilities"][ability_name_en]["value"] = get_int_value(ability_elem)

def parse_traits(root, json_data):
    """特徴をXMLからJSONにマッピングします。"""
    traits_mapping = {
        "尊ぶもの": "ideal",
        "人格的特徴": "trait",
        "関わり深いもの": "bond",
        "弱味": "flaw",
    }
    traits_elem = root.find(".//data[@name='特徴等']")
    if traits_elem is not None:
        for trait_elem in traits_elem.findall("data"):
            xml_name = trait_elem.get("name")
            json_name = traits_mapping.get(xml_name)
            if json_name:
                json_data["system"]["details"][json_name] = get_text(trait_elem)

def parse_items(root, json_data):
    """アイテムをXMLからJSONにマッピングします。"""
    items_elem = root.find(".//data[@name='アイテム']")
    if items_elem is not None:
        for item_elem in items_elem.findall("data"):
            item_name = item_elem.get("name")
            json_data["items"].append({
                "name": item_name,
                "type": "item",
                "system": {"description": {"value": get_text(item_elem)}}
            })

def xml_to_fvtt_json(xml_string):
    """ユドナリウム形式のXML文字列をFVTT用のJSONデータに変換します。"""
    try:
        root = etree.fromstring(xml_string.encode("utf-8"))

        json_data = {
            "name": "",
            "type": "character",
            "system": {
                "abilities": {key: {"value": 0} for key in ["str", "dex", "con", "int", "wis", "cha"]},
                "attributes": {"hp": {"value": 0, "max": 0}, "hd": {"value": ""}},
                "details": {"alignment": "", "race": "", "biography": {"value": ""}},
                "spells": {f"spell{level}": {"value": 0, "max": 0} for level in range(1, 10)}
            },
            "items": []
        }

        # キャラクター名
        name_elem = root.find(".//data[@name='character']/data[@name='name']")
        json_data["name"] = get_text(name_elem)

        # 各種データのパース
        parse_abilities(root, json_data)
        hp_elem = root.find(".//data[@name='行動データ']/data[@name='ヒット・ポイント']")
        if hp_elem is not None:
            json_data["system"]["attributes"]["hp"]["value"] = get_int_value(hp_elem, "currentValue")
            json_data["system"]["attributes"]["hp"]["max"] = get_int_value(hp_elem)
        
        hit_dice_elem = root.find(".//data[@name='ヒット・ダイス']")
        json_data["system"]["attributes"]["hd"]["value"] = get_text(hit_dice_elem)
        
        alignment_elem = root.find(".//data[@name='属性']")
        json_data["system"]["details"]["alignment"] = get_text(alignment_elem)
        
        race_elem = root.find(".//data[@name='種族']")
        json_data["system"]["details"]["race"] = get_text(race_elem)

        for level_num in range(1, 10):
            xml_level_name = f"LV{level_num}"
            slot_elem = root.find(f".//data[@name='{xml_level_name}']/data[@name='スロット']")
            if slot_elem is not None:
                json_data["system"]["spells"][f"spell{level_num}"]["value"] = get_int_value(slot_elem, "currentValue")
                json_data["system"]["spells"][f"spell{level_num}"]["max"] = get_int_value(slot_elem)

        parse_traits(root, json_data)
        parse_items(root, json_data)

        # 変換できないデータをbiographyに追加
        skip_names = set([
            "基本", "能力値", "行動データ", "技能", "セーヴィングスロー",
            "特徴等", "imageIdentifier", "ヒット・ダイス", "ヒット・ポイント",
            "属性", "種族", "アイテム"
        ])
        unconverted_data = []
        detail_elem = root.find(".//data[@name='detail']")
        if detail_elem is not None:
            for data_elem in detail_elem.findall(".//data"):
                name = data_elem.get("name")
                if not name or name in skip_names or not data_elem.text:
                    continue
                unconverted_data.append(f"{name}: {data_elem.text.strip()}")

        if unconverted_data:
            json_data["system"]["details"]["biography"]["value"] = "\n".join(unconverted_data)

        return json_data

    except etree.XMLSyntaxError as e:
        logger.error(f"XML構文エラー: {e}")
        return None
    except Exception as e:
        logger.error(f"変換中に予期しないエラー: {e}", exc_info=True)
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ユドナリウムXMLをFVTT JSONに変換します。")
    parser.add_argument("input_xml_filename", help="入力XMLファイルのパス")
    args = parser.parse_args()

    input_filename = args.input_xml_filename
    base_filename, ext = os.path.splitext(os.path.basename(input_filename))
    output_filename = f"2converted_{base_filename}.json"

    if ext.lower() != ".xml":
        logger.error("入力ファイルはXML形式である必要があります。")
        sys.exit(1)

    try:
        with open(input_filename, "r", encoding="utf-8") as f:
            xml_data = f.read()
    except FileNotFoundError:
        logger.error(f"ファイルが見つかりません: {input_filename}")
        sys.exit(1)

    converted_json = xml_to_fvtt_json(xml_data)
    if converted_json:
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(converted_json, f, indent=4, ensure_ascii=False)
        logger.info(f"XMLをJSONに正常に変換しました。出力ファイル: {output_filename}")
    else:
        logger.error("変換に失敗しました。")import argparse
import json
import logging
import os
import sys
from lxml import etree

# ロギングの設定
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def get_text(elem):
    """要素からテキストを安全に取得します。"""
    return elem.text.strip() if elem is not None and elem.text else ""

def get_int_value(elem, attrib_name="text"):
    """要素から整数値を安全に取得します。"""
    if elem is None:
        return 0
    value = elem.get(attrib_name) if attrib_name != "text" else elem.text
    try:
        return int(value.strip()) if value else 0
    except (ValueError, AttributeError):
        return 0

def parse_abilities(root, json_data):
    """能力値をXMLからJSONにマッピングします。"""
    ability_mapping = {
        "筋力": "str",
        "敏捷力": "dex",
        "耐久力": "con",
        "知力": "int",
        "判断力": "wis",
        "魅力": "cha",
    }
    for ability_elem in root.findall(".//data[@name='能力値']/data"):
        ability_name_jp = ability_elem.get("name", "").replace("【", "").replace("】", "")
        ability_name_en = ability_mapping.get(ability_name_jp)
        if ability_name_en:
            json_data["system"]["abilities"][ability_name_en]["value"] = get_int_value(ability_elem)

def parse_traits(root, json_data):
    """特徴をXMLからJSONにマッピングします。"""
    traits_mapping = {
        "尊ぶもの": "ideal",
        "人格的特徴": "trait",
        "関わり深いもの": "bond",
        "弱味": "flaw",
    }
    traits_elem = root.find(".//data[@name='特徴等']")
    if traits_elem is not None:
        for trait_elem in traits_elem.findall("data"):
            xml_name = trait_elem.get("name")
            json_name = traits_mapping.get(xml_name)
            if json_name:
                json_data["system"]["details"][json_name] = get_text(trait_elem)

def parse_items(root, json_data):
    """アイテムをXMLからJSONにマッピングします。"""
    items_elem = root.find(".//data[@name='アイテム']")
    if items_elem is not None:
        for item_elem in items_elem.findall("data"):
            item_name = item_elem.get("name")
            json_data["items"].append({
                "name": item_name,
                "type": "item",
                "system": {"description": {"value": get_text(item_elem)}}
            })

def xml_to_fvtt_json(xml_string):
    """ユドナリウム形式のXML文字列をFVTT用のJSONデータに変換します。"""
    try:
        root = etree.fromstring(xml_string.encode("utf-8"))

        json_data = {
            "name": "",
            "type": "character",
            "system": {
                "abilities": {key: {"value": 0} for key in ["str", "dex", "con", "int", "wis", "cha"]},
                "attributes": {"hp": {"value": 0, "max": 0}, "hd": {"value": ""}},
                "details": {"alignment": "", "race": "", "biography": {"value": ""}},
                "spells": {f"spell{level}": {"value": 0, "max": 0} for level in range(1, 10)}
            },
            "items": []
        }

        # キャラクター名
        name_elem = root.find(".//data[@name='character']/data[@name='name']")
        json_data["name"] = get_text(name_elem)

        # 各種データのパース
        parse_abilities(root, json_data)
        hp_elem = root.find(".//data[@name='行動データ']/data[@name='ヒット・ポイント']")
        if hp_elem is not None:
            json_data["system"]["attributes"]["hp"]["value"] = get_int_value(hp_elem, "currentValue")
            json_data["system"]["attributes"]["hp"]["max"] = get_int_value(hp_elem)
        
        hit_dice_elem = root.find(".//data[@name='ヒット・ダイス']")
        json_data["system"]["attributes"]["hd"]["value"] = get_text(hit_dice_elem)
        
        alignment_elem = root.find(".//data[@name='属性']")
        json_data["system"]["details"]["alignment"] = get_text(alignment_elem)
        
        race_elem = root.find(".//data[@name='種族']")
        json_data["system"]["details"]["race"] = get_text(race_elem)

        for level_num in range(1, 10):
            xml_level_name = f"LV{level_num}"
            slot_elem = root.find(f".//data[@name='{xml_level_name}']/data[@name='スロット']")
            if slot_elem is not None:
                json_data["system"]["spells"][f"spell{level_num}"]["value"] = get_int_value(slot_elem, "currentValue")
                json_data["system"]["spells"][f"spell{level_num}"]["max"] = get_int_value(slot_elem)

        parse_traits(root, json_data)
        parse_items(root, json_data)

        # 変換できないデータをbiographyに追加
        skip_names = set([
            "基本", "能力値", "行動データ", "技能", "セーヴィングスロー",
            "特徴等", "imageIdentifier", "ヒット・ダイス", "ヒット・ポイント",
            "属性", "種族", "アイテム"
        ])
        unconverted_data = []
        detail_elem = root.find(".//data[@name='detail']")
        if detail_elem is not None:
            for data_elem in detail_elem.findall(".//data"):
                name = data_elem.get("name")
                if not name or name in skip_names or not data_elem.text:
                    continue
                unconverted_data.append(f"{name}: {data_elem.text.strip()}")

        if unconverted_data:
            json_data["system"]["details"]["biography"]["value"] = "\n".join(unconverted_data)

        return json_data

    except etree.XMLSyntaxError as e:
        logger.error(f"XML構文エラー: {e}")
        return None
    except Exception as e:
        logger.error(f"変換中に予期しないエラー: {e}", exc_info=True)
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ユドナリウムXMLをFVTT JSONに変換します。")
    parser.add_argument("input_xml_filename", help="入力XMLファイルのパス")
    args = parser.parse_args()

    input_filename = args.input_xml_filename
    base_filename, ext = os.path.splitext(os.path.basename(input_filename))
    output_filename = f"2converted_{base_filename}.json"

    if ext.lower() != ".xml":
        logger.error("入力ファイルはXML形式である必要があります。")
        sys.exit(1)

    try:
        with open(input_filename, "r", encoding="utf-8") as f:
            xml_data = f.read()
    except FileNotFoundError:
        logger.error(f"ファイルが見つかりません: {input_filename}")
        sys.exit(1)

    converted_json = xml_to_fvtt_json(xml_data)
    if converted_json:
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(converted_json, f, indent=4, ensure_ascii=False)
        logger.info(f"XMLをJSONに正常に変換しました。出力ファイル: {output_filename}")
    else:
        logger.error("変換に失敗しました。")
