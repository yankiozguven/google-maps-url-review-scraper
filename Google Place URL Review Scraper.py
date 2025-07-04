#!/usr/bin/env python3
import os
import time
import re
import uuid
import random
import string
from playwright.sync_api import sync_playwright, expect, TimeoutError # type: ignore
import pandas as pd
from slugify import slugify # type: ignore
from datetime import datetime
from tqdm import tqdm

def generate_random_id(length=8):
    """Unique ID oluştur"""
    letters = string.ascii_lowercase + string.digits
    return ''.join(random.choice(letters) for i in range(length))

def scrape_google_maps(url, max_reviews=100, sort_by="newest"):
    # Benzersiz bir ID oluştur
    session_id = generate_random_id()
    print(f"Google Maps verisi çekiliyor... (Sıralama: {sort_by}, Maksimum yorum: {max_reviews}, İşlem ID: {session_id})")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={'width': 1366, 'height': 768},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        # URL'ye git
        try:
            page.goto(url, wait_until="networkidle")
        except:
            page.goto(url, wait_until="load")
            
        # Çerezleri kabul et (gerekirse)
        try:
            accept_button = page.get_by_role("button", name=re.compile("(Kabul|Accept|Tümünü kabul|Agree)", re.IGNORECASE))
            if accept_button:
                accept_button.click(timeout=5000)
                time.sleep(2)
        except:
            pass
                
        # Sayfanın tamamen yüklenmesi için bekle
        time.sleep(5)
        
        # Mekan ismini al - daha sağlam yöntemlerle
        place_name = ""
        try:
            # Daha fazla şans vermek için sayfanın yüklenmesini bekle
            time.sleep(5)
            
            # Birkaç farklı seçici dene
            selectors = [
                'h1.DUwDvf',  # En çok kullanılan h1 sınıfı
                'h1',  # Herhangi bir h1
                '[role="main"] h1', 
                'header h1', 
                'div[role="main"] div[role="heading"]', 
                'div.fontHeadlineLarge',
                'div.tAiQdd',
                'div.kSQYJe',
                'div[data-attrid] span'  # Bilgi panelindeki isim
            ]
            
            for selector in selectors:
                try:
                    place_name_elements = page.locator(selector).all()
                    for elem in place_name_elements:
                        text = elem.text_content().strip()
                        if text and len(text) >= 3 and len(text) < 100:
                            # Yapılan kontrollerle, gerçekten isim mi diye kontrol et
                            # Tipik olarak restoran isimleri linklerde olmaz
                            if not elem.locator('a').count() and not re.search(r'http|www|\.(com|net|org)', text.lower()):
                                place_name = text
                                print(f"Mekan bulundu: {place_name}")
                                break
                    if place_name:
                        break
                except:
                    continue
            
            # Hala bulunamadıysa, sayfa başlığından almayı dene
            if not place_name:
                try:
                    title = page.title()
                    # Başlık genellikle "Restoran İsmi - Google Haritalar" formatındadır
                    if " - " in title:
                        place_name = title.split(" - ")[0].strip()
                        print(f"Mekan başlıktan bulundu: {place_name}")
                except:
                    pass
            
            # Son çare olarak, herhangi bir title veya h1 içeriğini al
            if not place_name:
                try:
                    # Meta bilgilerinden al
                    meta_title = page.locator('meta[property="og:title"]').get_attribute('content')
                    if meta_title:
                        # "xxx - Google Haritalar" formatını temizle
                        place_name = re.sub(r' - Google (Haritalar|Maps)$', '', meta_title).strip()
                        print(f"Mekan meta bilgisinden bulundu: {place_name}")
                except:
                    # Herhangi bir heading bul
                    try:
                        all_h1 = page.locator('h1, [role="heading"][aria-level="1"]').all()
                        for h in all_h1:
                            text = h.text_content().strip()
                            if text and len(text) >= 3 and len(text) < 100:
                                place_name = text
                                print(f"Mekan herhangi bir başlıktan bulundu: {place_name}")
                                break
                    except:
                        pass
            
            # Cümle içinde geçen "Maps" kelimesini temizle
            if place_name and ("Maps" in place_name or "Haritalar" in place_name):
                place_name = re.sub(r' - Google (Haritalar|Maps)$', '', place_name).strip()
            
            if not place_name:
                place_name = "Bilinmeyen_Mekan"
                print("Mekan adı bulunamadı, varsayılan isim kullanılıyor")
        except Exception as e:
            place_name = "Bilinmeyen_Mekan"
            print(f"Mekan adı alınamadı: {e}")
        
        # Klasör oluştur (mekan adı + random ID ile)
        folder_name = f"{slugify(place_name)}_{session_id}"
        folder_path = os.path.join(os.path.expanduser("~/Downloads"), folder_name)
        os.makedirs(folder_path, exist_ok=True)
        print(f"Veriler şu klasörde toplanacak: {folder_path}")
        
        # Debug için ekran görüntüsü al
        try:
            page.screenshot(path=os.path.join(folder_path, "main_page.png"), full_page=True)
        except:
            pass
        
        # ===== Restoran genel bilgilerini topla (iyileştirilmiş) =====
        general_info = {
            'Mekan_Adi': [place_name],
            'Puan': [""],
            'Yorum_Sayisi': [""],
            'Adres': [""],
            'Telefon': [""],
            'Web_Sitesi': [""],
            'Kategori': [""],
            'Fiyat_Seviyesi': [""],
            'Calisma_Saatleri': [""]
        }
        
        print("Genel bilgiler toplanıyor...")
        
        # Önce ana sayfaya veya genel bakış sekmesine geçmeye çalışalım
        try:
            for selector in [
                'button[data-tab-index="0"]',
                'button:has-text("Genel bakış")',
                'button:has-text("Ana bilgiler")',
                'div[role="tab"]:has-text("Genel")'
            ]:
                try:
                    elements = page.locator(selector).all()
                    for element in elements:
                        if "genel" in element.text_content().lower() or "ana" in element.text_content().lower() or "bakış" in element.text_content().lower():
                            element.click(timeout=3000)
                            print("Ana bilgiler sekmesine geçildi")
                            time.sleep(2)
                            break
                except:
                    continue
        except:
            pass
        
        # Daha çok veri görmek için ekranı biraz kaydır
        page.mouse.wheel(0, 300)
        time.sleep(1)
        
        # Kategori bilgisini al
        try:
            for selector in [
                'button[jsaction*="category"] span',
                'div[jsaction*="category"]',
                'span.DkEaL',
                'span[jstcache*="category"]',
                'div.cX2WmPgCkHi__section-info-text',
                'div.fontBodyMedium span', 
                'button[aria-label*="işletme kategorisi"]',
                'span.YhemCb'
            ]:
                try:
                    elements = page.locator(selector).all()
                    for element in elements:
                        text = element.text_content().strip()
                        if text and len(text) > 2 and len(text) < 50 and not re.search(r'\d', text):
                            # Restoran, Kafe gibi kategorileri içeriyor mu kontrol et
                            if any(keyword in text.lower() for keyword in ["restoran", "kafe", "cafe", "bar", "pub", "lokanta", "bistro", "pizzeria", "kebap"]):
                                general_info['Kategori'] = [text]
                                print(f"Kategori: {text}")
                                break
                    if general_info['Kategori'] != [""]:
                        break
                except:
                    continue
        except Exception as e:
            print(f"Kategori alınamadı: {e}")
        
        # Puanı al (daha güvenilir)
        try:
            rating_found = False
            
            # Birinci yöntem: Başlık yanındaki büyük puan
            for selector in [
                'span.fontDisplayLarge', 
                'div.F7nice',
                'span.ceNzKf',
                'span[aria-hidden="true"]',
                '[role="img"][aria-label*="yıldız"]',
                '[aria-label*="yıldız"]',
                'div[role="img"]'
            ]:
                try:
                    elements = page.locator(selector).all()
                    for element in elements:
                        text = element.text_content().strip()
                        if text and re.search(r'[0-9]', text) and len(text) < 5:
                            # 1 ile 5 arasında bir puan olduğunu doğrula
                            if re.search(r'[1-5]', text):
                                # Virgül içeren metinlerde (4,7 gibi) nokta ile değiştir
                                if ',' in text:
                                    text = text.replace(',', '.')
                                
                                # Sadece sayı içeren metinlerde küsurat yoksa .0 ekle
                                if text.isdigit() and len(text) == 1:
                                    text = text + '.0'
                                
                                general_info['Puan'] = [text]
                                print(f"Puan: {text}")
                                rating_found = True
                                break
                    if rating_found:
                        break
                except:
                    continue
            
            # İkinci yöntem: Puan yanındaki yıldız ikonlarından çıkarma
            if not rating_found:
                for star_selector in [
                    'aria-label*="stars"',
                    'aria-label*="star"',
                    'aria-label*="yıldız"',
                    '[role="img"][aria-label]'
                ]:
                    try:
                        star_elements = page.locator(f'[{star_selector}]').all()
                        for star_elem in star_elements:
                            aria_label = star_elem.get_attribute('aria-label')
                            if aria_label:
                                # "4.5 stars" veya "4,5 yıldız" formatlarını bul
                                star_match = re.search(r'([0-9][.,][0-9]|[0-9])\s*(stars|star|yıldız|puan)', aria_label.lower())
                                if star_match:
                                    # Standardize et (nokta kullan, virgül değil)
                                    rating_text = star_match.group(1).replace(',', '.')
                                    general_info['Puan'] = [rating_text]
                                    print(f"Puan (yıldız ikonundan): {rating_text}")
                                    rating_found = True
                                    break
                        if rating_found:
                            break
                    except:
                        continue
            
            # Üçüncü yöntem: Sayfa içeriğinde "5 üzerinden X" gibi ifadeler ara
            if not rating_found:
                rating_patterns = [
                    r'([0-9],[0-9]) üzerinden 5',
                    r'([0-9]\.[0-9]) out of 5',
                    r'([0-9],[0-9])/5',
                    r'5 üzerinden ([0-9],[0-9])',
                    r'5 out of ([0-9]\.[0-9])'
                ]
                
                page_text = page.content()
                for pattern in rating_patterns:
                    match = re.search(pattern, page_text)
                    if match:
                        # Grup 1'i al, eğer yoksa grup 0'ı al
                        rating_text = match.group(1) if match.group(1) else match.group(0)
                        rating_text = rating_text.replace(',', '.')
                        general_info['Puan'] = [rating_text]
                        print(f"Puan (metin içinden): {rating_text}")
                        rating_found = True
                        break
            
            # Dördüncü yöntem: Sayfa başlığından çıkarma
            if not rating_found:
                try:
                    title = page.title()
                    # "Restaurant Name - 4.5 (123 reviews)" formatı
                    title_match = re.search(r'([0-9][.,][0-9]|[0-9])\s*\(', title)
                    if title_match:
                        rating_text = title_match.group(1).replace(',', '.')
                        general_info['Puan'] = [rating_text]
                        print(f"Puan (başlıktan): {rating_text}")
                        rating_found = True
                except:
                    pass
            
            # Eğer hala bulunamadıysak, sayfadaki tüm potansiyel puan metinlerini ara
            if not rating_found:
                all_texts = page.locator('span, div').all()
                for elem in all_texts:
                    try:
                        text = elem.text_content().strip()
                        # "4.5" veya "4,5" formatında bir metin ara
                        if re.match(r'^[0-9][.,][0-9]$', text) or re.match(r'^[1-5]$', text):
                            rating_text = text.replace(',', '.')
                            general_info['Puan'] = [rating_text]
                            print(f"Puan (genel arama): {rating_text}")
                            rating_found = True
                            break
                    except Exception:
                        pass
        except Exception as e:
            print(f"Puan alınamadı: {e}")
        
        # Yorum sayısını al
        try:
            for selector in [
                'div.fontBodyMedium span:has-text("review")',
                'span.UY7F9',
                'button[data-tab-index="1"] div',
                'span:has-text("yorum")',
                'span:has-text("değerlendirme")',
                'span.F7nice',
                'div[aria-label*="yorum"]'
            ]:
                try:
                    elements = page.locator(selector).all()
                    for element in elements:
                        text = element.text_content().strip()
                        if re.search(r'[0-9]', text) and ("yorum" in text.lower() or "review" in text.lower() or "değerlendirme" in text.lower()):
                            # Sadece rakamı almak için regex kullan
                            nums = re.findall(r'[0-9]+', text)
                            if nums:
                                review_count = ''.join(nums)
                                general_info['Yorum_Sayisi'] = [f"{review_count} yorum"]
                                print(f"Yorum sayısı: {review_count}")
                                break
                    if general_info['Yorum_Sayisi'] != [""]:
                        break
                except:
                    continue
        except Exception as e:
            print(f"Yorum sayısı alınamadı: {e}")
            
        # Adresi al
        try:
            address_found = False
            for selector in [
                'button[data-item-id="address"]',
                'button[aria-label*="adres"]',
                'button[data-tooltip="Adresi kopyala"]',
                'button:has-text("Adres")',
                'div:has-text("Adres") ~ div',
                'button[jsaction*="si_address"]',
                'div[jsaction*="si_address"]'
            ]:
                try:
                    elements = page.locator(selector).all()
                    for element in elements:
                        text = element.text_content().strip()
                        if text and len(text) > 10:
                            general_info['Adres'] = [text]
                            print(f"Adres: {text}")
                            address_found = True
                            break
                    if address_found:
                        break
                except:
                    continue
                    
            # Alternatif: Adres bilgisinin görüntülendiği butonu tıkla
            if not address_found:
                address_buttons = page.locator('button:has-text("Adres"), button[jsaction*="address"]').all()
                for button in address_buttons:
                    try:
                        button.click(timeout=2000)
                        time.sleep(1)
                        # Tıklamadan sonra popup içinde adresi ara
                        address_texts = page.locator('div[role="dialog"] div').all()
                        for elem in address_texts:
                            text = elem.text_content().strip()
                            if text and len(text) > 15 and ("cadde" in text.lower() or "sokak" in text.lower() or "mah" in text.lower()):
                                general_info['Adres'] = [text]
                                print(f"Adres (alternatif): {text}")
                                # Popupı kapat
                                page.keyboard.press("Escape")
                                address_found = True
                                break
                        if address_found:
                            break
                    except:
                        continue
        except Exception as e:
            print(f"Adres alınamadı: {e}")
            
        # Telefon numarası al
        try:
            for selector in [
                'button[data-tooltip="Telefon numarasını kopyala"]', 
                'button[aria-label*="telefon"]',
                'div:has-text("Telefon") ~ div',
                'button:has-text("Telefon")',
                'span:has-text("Telefon") + span',
                'button[jsaction*="phone"]',
                'div[jsaction*="phone"]'
            ]:
                try:
                    elements = page.locator(selector).all()
                    for element in elements:
                        text = element.text_content().strip()
                        if text and (re.search(r'[0-9]', text) or "+" in text):
                            # Numarayı düzgün formatla
                            if len(text) >= 10:  # Geçerli telefon numarası en az 10 karakter olmalı
                                general_info['Telefon'] = [text]
                                print(f"Telefon: {text}")
                                break
                    if general_info['Telefon'] != [""]:
                        break
                except:
                    continue
                    
            # Alternatif: Telefon bilgisinin görüntülendiği butonu tıkla
            if general_info['Telefon'] == [""]:
                phone_buttons = page.locator('button:has-text("Telefon"), button[jsaction*="phone"]').all()
                for button in phone_buttons:
                    try:
                        button.click(timeout=2000)
                        time.sleep(1)
                        # Tıklamadan sonra popup içinde telefonu ara
                        phone_texts = page.locator('div[role="dialog"] div').all()
                        for elem in phone_texts:
                            text = elem.text_content().strip()
                            if text and re.search(r'[0-9]', text) and len(text) >= 10:
                                general_info['Telefon'] = [text]
                                print(f"Telefon (alternatif): {text}")
                                # Popup'ı kapat
                                page.keyboard.press("Escape")
                                break
                        if general_info['Telefon'] != [""]:
                            break
                    except:
                        continue
        except Exception as e:
            print(f"Telefon alınamadı: {e}")
        
        # Fiyat seviyesini kişi başı fiyat üzerinden al
        try:
            price_found = False
            # Öncelik: kişi başı fiyatı arayalım
            per_person_keywords = [
                "kişi başı", "kişi başı fiyat", "kişi başı ücret", "kişi başı maliyet", "kişi başı ortalama",
                "per person", "per-person", "per head", "per capita", "per guest"
            ]
            for keyword in per_person_keywords:
                try:
                    elements = page.locator(f'span:has-text("{keyword}"), div:has-text("{keyword}"), *:has-text("{keyword}")').all()
                    for element in elements:
                        text = element.text_content().strip()
                        if keyword in text.lower() and len(text) < 50:
                            general_info['Fiyat_Seviyesi'] = [text]
                            print(f"Kişi başı fiyat bulundu: {text}")
                            price_found = True
                            break
                    if price_found:
                        break
                except:
                    continue
            
            # Eğer kişi başı fiyat bulunamazsa, eski yöntemlerle devam et
            if not price_found:
                # Metot 1: Doğrudan fiyat seviyesi içeren elementleri bul
                for selector in [
                    'span:has-text("₺")',
                    'span.mgr77e',
                    'span:has-text("Fiyat") + span',
                    'span[aria-label*="fiyat"]',
                    'div[jsaction*="price"]',
                    'span[aria-label*="price"]',
                    'span[class*="price"]'
                ]:
                    try:
                        elements = page.locator(selector).all()
                        for element in elements:
                            text = element.text_content().strip()
                            if "₺" in text and len(text) <= 5:
                                general_info['Fiyat_Seviyesi'] = [text]
                                print(f"Fiyat seviyesi: {text}")
                                price_found = True
                                break
                        if price_found:
                            break
                    except Exception as e:
                        print(f"Fiyat elementi aranırken hata: {e}")
                        continue
                
                # Metot 2: Fiyat kategorisi içeren elementleri bul
                if not price_found:
                    price_indicators = [
                        "ucuz", "cheap", "inexpensive", 
                        "ekonomik", "orta", "moderate", 
                        "pahalı", "lüks", "expensive", "luxury"
                    ]
                    
                    for indicator in price_indicators:
                        try:
                            elements = page.locator(f'span:has-text("{indicator}"), div:has-text("{indicator}")').all()
                            for element in elements:
                                text = element.text_content().strip()
                                if len(text) < 30:  # Kısa metinler, muhtemelen fiyat bilgisi
                                    general_info['Fiyat_Seviyesi'] = [text]
                                    print(f"Fiyat seviyesi (açıklama): {text}")
                                    price_found = True
                                    break
                        except:
                            continue
                        
                        if price_found:
                            break
                            
                # Metot 3: Fiyat aralığı içeren elementleri bul
                if not price_found:
                    price_range_patterns = [
                        r'([₺$€£]{1,4})\s*[-–]\s*([₺$€£]{1,4})',  # ₺₺ - ₺₺₺ format
                        r'([₺$€£]{1,4})[-–]([₺$€£]{1,4})'          # ₺₺-₺₺₺ format
                    ]
                    
                    try:
                        page_text = page.content()
                        for pattern in price_range_patterns:
                            match = re.search(pattern, page_text)
                            if match:
                                price_text = match.group(0)
                                general_info['Fiyat_Seviyesi'] = [price_text]
                                print(f"Fiyat aralığı: {price_text}")
                                price_found = True
                                break
                    except Exception as e:
                        print(f"Fiyat aralığı araması sırasında hata: {e}")
                            
            # Eğer hala bulunamadıysa, bara bir şey yaz
            if not price_found or general_info['Fiyat_Seviyesi'] == [""]:
                general_info['Fiyat_Seviyesi'] = ["Belirtilmemiş"]
        except Exception as e:
            print(f"Fiyat seviyesi alınamadı: {e}")
            general_info['Fiyat_Seviyesi'] = ["Belirtilmemiş"]
        
        # Çalışma saatlerini al - geliştirilmiş metot
        try:
            hours_text = ""
            days_info = {}
            
            # Önce "Çalışma saatleri" metnini içeren butonu bul
            hours_button = None
            for selector in [
                'button[data-item-id="oh"]',
                'button:has-text("Çalışma saatleri")',
                'div:has-text("Çalışma saatleri") button',
                'button[aria-label*="saat"]',
                'button[jsaction*="hours"]',
                'div[jsaction*="hours"]',
                'div:has-text("Bugün") + div',  # "Bugün XX:XX - XX:XX" formatına sahip elementler
                'div:has-text("Açık") + div'    # "Açık · XX:XX kapanıyor" formatına sahip elementler
            ]:
                try:
                    elements = page.locator(selector).all()
                    for element in elements:
                        content = element.text_content().lower()
                        if ("saat" in content or "açık" in content or "kapalı" in content or 
                            "bugün" in content or (":" in content and ("-" in content or "–" in content))):
                            hours_button = element
                            print(f"Çalışma saatleri butonu bulundu: '{content}'")
                            break
                    if hours_button:
                        break
                except:
                    continue
            
            # Butonu bulamadıysak, direkt sayfada saatleri arayalım
            if not hours_button:
                today_pattern = r'(Bugün|Today).*?(\d{1,2}[:.]\d{2}).*?[-–].*?(\d{1,2}[:.]\d{2})'
                page_text = page.content().lower()
                today_match = re.search(today_pattern, page_text)
                if today_match:
                    today_hours = f"Bugün: {today_match.group(2)} - {today_match.group(3)}"
                    print(f"Bugünün çalışma saati bulundu: {today_hours}")
                    hours_text = today_hours
                    days_info = {"Bugün": f"{today_match.group(2)} - {today_match.group(3)}"}
            
            # Bulunan butona tıklayarak detaylı saatleri al
            full_schedule_found = False
            if hours_button and not hours_text:
                try:
                    hours_button.click(timeout=3000)
                    time.sleep(2)
                    
                    # Çalışma saatleri popupını bul
                    for panel_selector in [
                        'div[role="dialog"]',
                        'div.m6QErb.tLjsW.eKbjU',
                        'table[class*="WgFkxc"]',
                        'div[aria-label*="Çalışma saatleri"]',
                        'div.OMl5r',
                        'div[role="dialog"] table',
                        'div[jsaction*="modal"]'
                    ]:
                        try:
                            panel = page.locator(panel_selector).first
                            if panel:
                                panel_content = panel.text_content().strip()
                                if ("pazartesi" in panel_content.lower() or "salı" in panel_content.lower() or
                                    "monday" in panel_content.lower() or "tuesday" in panel_content.lower()):
                                    
                                    # Haftanın her günü için saatleri bul
                                    days = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar",
                                            "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                                    
                                    days_pattern = '|'.join(days)
                                    day_matches = re.findall(rf'({days_pattern})[\s:]*([^a-zA-Z\n]+)', panel_content, re.IGNORECASE)
                                    
                                    if day_matches:
                                        for day, hours in day_matches:
                                            # Saatleri temizle
                                            hours = re.sub(r'\s+', ' ', hours).strip()
                                            
                                            # Gün adını Türkçe'ye standardize et
                                            day_map = {
                                                "Monday": "Pazartesi", "Tuesday": "Salı", "Wednesday": "Çarşamba",
                                                "Thursday": "Perşembe", "Friday": "Cuma", "Saturday": "Cumartesi", "Sunday": "Pazar"
                                            }
                                            
                                            tr_day = day_map.get(day, day)
                                            days_info[tr_day] = hours
                                        
                                        # Tüm günleri sıralı şekilde birleştir
                                        ordered_days = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
                                        hours_parts = []
                                        
                                        for day in ordered_days:
                                            if day in days_info:
                                                hours_parts.append(f"{day}: {days_info[day]}")
                                        
                                        if hours_parts:
                                            hours_text = "\n".join(hours_parts)
                                            full_schedule_found = True
                                            print("Çalışma saatleri tüm günler için alındı")
                                    
                                    # Pattern bulamazsa, ham metni kullan
                                    if not full_schedule_found:
                                        hours_text = panel_content
                                        print("Çalışma saatleri ham metin olarak alındı")
                                    
                                    # Dialogu kapat
                                    page.keyboard.press("Escape")
                                    break
                        except Exception as e:
                            print(f"Panel içeriği alınırken hata: {e}")
                            continue
                except Exception as e:
                    print(f"Çalışma saatleri butonuna tıklamada hata: {e}")
            
            # Hala bulunamadıysa, özel formatları kontrol et
            if not hours_text:
                # Sayfa içerisinde çalışma saatleri bilgisini içeren bölüm var mı diye arat
                for selector in [
                    'div:has-text("Pazartesi") ~ div',
                    'div:has-text("Monday") ~ div',
                    'div:has-text("Çalışma saatleri") ~ div',
                    'div[class*="hour"]',
                    'div[jslog*="hours"]',
                    'table:has(tr:has-text("Pazartesi"))',
                    'table:has(tr:has-text("Monday"))'
                ]:
                    try:
                        elements = page.locator(selector).all()
                        for element in elements:
                            text = element.text_content().strip()
                            # Hem gün adı hem de saat içeriyor mu kontrol et
                            if (("pazartesi" in text.lower() or "monday" in text.lower()) and
                                (":" in text) and len(text) > 20):
                                hours_text = text
                                print("Çalışma saatleri sayfa içinden alındı")
                                break
                        if hours_text:
                            break
                    except Exception as e:
                        print(f"Çalışma saatleri elemanı araması sırasında hata: {e}")
                        continue
            
            # Çalışma saatlerini düzenle
            if hours_text:
                # Gereksiz boşlukları temizle
                hours_text = re.sub(r'\s+', ' ', hours_text)
                
                # Saatleri daha okunabilir hale getir
                if not full_schedule_found:  # Eğer tam düzenli format elde edemediyse
                    days = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar",
                            "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                    
                    for day in days:
                        hours_text = re.sub(rf'({day})', r'\n\1', hours_text, flags=re.IGNORECASE)
                
                # Başındaki gereksiz boşlukları temizle
                hours_text = hours_text.strip()
                
                general_info['Calisma_Saatleri'] = [hours_text]
                print(f"Çalışma saatleri kaydedildi ({len(hours_text)} karakter)")
            else:
                general_info['Calisma_Saatleri'] = ["Belirtilmemiş"]
                print("Çalışma saatleri bulunamadı")
        except Exception as e:
            print(f"Çalışma saatleri alınamadı: {e}")
            general_info['Calisma_Saatleri'] = ["Hata: Alınamadı"]
        
        # Web sitesi al (ana sayfadan)
        try:
            for selector in [
                'a[data-tooltip="Web sitesi"]', 
                'a[aria-label*="web"]',
                'div:has-text("Web sitesi") ~ div a',
                'a:has-text("Web sitesi")',
                'a[href*="http"]:not([href*="google"])',
                'a[jsaction*="website"]',
                'div[jsaction*="website"] a'
            ]:
                try:
                    elements = page.locator(selector).all()
                    for element in elements:
                        text = element.text_content().strip()
                        href = element.get_attribute("href")
                        if (text and ("http" in text.lower() or "www" in text.lower() or ".com" in text.lower() or ".net" in text.lower())) or (href and ("http" in href.lower() and "google" not in href.lower())):
                            website = text or href
                            # Google Translate URL'lerini filtrele
                            if "translate.google.com" not in website:
                                general_info['Web_Sitesi'] = [website]
                                print(f"Web sitesi: {website}")
                                break
                    if general_info['Web_Sitesi'] != [""]:
                        break
                except:
                    continue
        except Exception as e:
            print(f"Web sitesi alınamadı: {e}")
        
        # Genel bilgileri kaydet
        pd.DataFrame(general_info).to_csv(os.path.join(folder_path, 'genel_bilgiler.csv'), index=False)
        print("Genel bilgiler kaydedildi.")
        
        # ===== Yorumlar sekmesine git =====
        try:
            # Yorumlar sekmesini bul ve tıkla
            review_tab_clicked = False
            for selector in [
                'button[data-tab-index="1"]',
                'button:has-text("Yorumlar")',
                'button:has-text("Değerlendirmeler")',
                'button:has-text("Reviews")',
                'div[role="tab"]:has-text("Yorum")',
                'div[role="tablist"] > div:nth-child(2)'
            ]:
                try:
                    elements = page.locator(selector).all()
                    for element in elements:
                        if "yorum" in element.text_content().lower() or "değerlendirme" in element.text_content().lower() or "review" in element.text_content().lower():
                            element.click(timeout=5000)
                            review_tab_clicked = True
                            print("Yorumlar sekmesine tıklandı")
                            time.sleep(3)
                            break
                    if review_tab_clicked:
                        break
                except:
                    continue
            
            if not review_tab_clicked:
                print("Yorumlar sekmesi bulunamadı, ana sayfada devam ediliyor.")
            
            # Ekran görüntüsü al (debug için)
            page.screenshot(path=os.path.join(folder_path, "reviews_tab.png"), full_page=True)
            
            # ===== Yorumları topla =====
            reviews = []
            print(f"Yorumlar toplanıyor... ({max_reviews} yorum hedefleniyor, sıralama: en yeni)")
            
            # "En yeni" sıralamayı bul ve seç - garantilemek için daha detaylı yaklaşım
            sort_by_newest_tried = False
            try:
                # Önce sıralama butonunu bul (birkaç kez deneyeceğiz)
                for attempt in range(3):
                    sort_button_found = False
                    
                    for selector in [
                        'button[aria-label*="Sıralama"]',
                        'button:has-text("Sırala")',
                        'button[aria-controls*="sort"]',
                        'button:has-text("Sort")',
                        'button[jsaction*="sort"]',
                        'div[role="button"]:has-text("Alakalı")',
                        'div[role="button"]:has-text("sırala")'
                    ]:
                        try:
                            sort_buttons = page.locator(selector).all()
                            for sort_button in sort_buttons:
                                try:
                                    text = sort_button.text_content().lower()
                                    if "sıra" in text or "sort" in text or "alak" in text or "en y" in text:
                                        sort_button.click(timeout=3000)
                                        sort_button_found = True
                                        print(f"Sıralama butonu bulundu ve tıklandı: '{text}'")
                                        time.sleep(2)
                                        break
                                except Exception as e:
                                    print(f"Sıralama butonuna tıklamada hata: {e}")
                                    continue
                            
                            if sort_button_found:
                                break
                        except:
                            continue
                    
                    if sort_button_found:
                        # Sıralama menüsü açıldı, şimdi "En yeni" seçeneğini bul
                        newest_option_found = False
                        
                        for newest_selector in [
                            'div[role="menuitem"]:has-text("En yeni")',
                            'div[role="menuitem"]:has-text("Yeni")',
                            'div[role="menuitem"]:has-text("Newest")',
                            'div[role="menuitem"]:has-text("Most recent")',
                            'div[role="menuitem"]:has-text("Recent")'
                        ]:
                            try:
                                options = page.locator(newest_selector).all()
                                for option in options:
                                    try:
                                        option_text = option.text_content().lower()
                                        if "yeni" in option_text or "recent" in option_text or "newest" in option_text:
                                            option.click(timeout=3000)
                                            newest_option_found = True
                                            sort_by_newest_tried = True
                                            print(f"EN YENİ sıralama seçildi: '{option_text}'")
                                            time.sleep(3)  # Yorumların yeniden yüklenmesi için daha uzun bekle
                                            break
                                    except:
                                        continue
                                
                                if newest_option_found:
                                    break
                            except:
                                continue
                        
                        if newest_option_found:
                            break
                        else:
                            # Menu açıldı ama en yeni bulunamadı, menüyü kapat ve tekrar dene
                            page.keyboard.press("Escape")
                            time.sleep(1)
                    
                    # Bulunamadıysa biraz bekle ve sayfayı tazele
                    if attempt < 2:  # Son denemede değilsek
                        page.mouse.wheel(0, 300)  # Biraz aşağı kaydır
                        time.sleep(2)
                
                if not sort_by_newest_tried:
                    print("En yeni sıralama seçeneği bulunamadı, varsayılan sıralama kullanılıyor")
            except Exception as e:
                print(f"Sıralama işlemi sırasında hata: {e}")
            
            # Daha fazla scroll yapmak için dinamik sayıda döngü
            # 200 yorum için daha fazla scroll
            scroll_count = max(40, int(max_reviews / 3))  # Her scroll'da ortalama 3 yorum yüklendiğini varsayalım
            
            # Scroll yaparak daha fazla yorum yükle
            print(f"Yorumları yüklemek için {scroll_count} kez kaydırma yapılacak...")
            
            # Yorumları yüklemek için scroll yapma
            for i in tqdm(range(scroll_count)):
                page.mouse.wheel(0, 1000)
                time.sleep(0.3)
                
                # Her 5 scroll'da bir daha uzun bekle
                if i % 5 == 4:
                    time.sleep(1)
                
                # Her 10 scroll'da bir kontrol et, eğer yeterli yorum yüklenmişse erken çık
                if i > 0 and i % 10 == 0:
                    try:
                        review_count = len(page.locator('div.jftiEf, div[data-review-id], div[jslog*="review"]').all())
                        print(f"Şu ana kadar {review_count} yorum yüklendi")
                        if review_count >= max_reviews * 1.2:  # Biraz fazladan yorum yükleyelim (bazıları filtreleneceği için)
                            print(f"Yeterli yorum yüklendi, scroll işlemi sonlandırılıyor")
                            break
                    except:
                        pass
            
            # Son bir scroll daha yap ve bekle
            page.mouse.wheel(0, 500)
            time.sleep(3)
            
            # Yorumları bul
            review_elements = []
            
            for selector in [
                'div.jftiEf',
                'div[data-review-id]',
                'div[jsaction*="reviewActionsGroup"]',
                'div[jslog*="review"]',
                'div.fontBodyMedium[style*="line-height"]',
                'div[class*="review"]',
                '[jsinstance*="review"]',
                'div[data-hveid]'
            ]:
                try:
                    found_elements = page.locator(selector).all()
                    if found_elements and len(found_elements) > 0:
                        print(f"{len(found_elements)} potansiyel yorum elementi bulundu: {selector}")
                        
                        # İçerik kontrolü yap
                        valid_elements = []
                        for elem in found_elements:
                            try:
                                # Yorum içeriği kontrolü
                                content = elem.text_content()
                                # Yıldız değeri kontrolü
                                has_star = elem.locator('span[role="img"], span[aria-label*="yıldız"], div[role="img"]').count() > 0
                                
                                if has_star and len(content) > 50:  # Mantıklı bir içerik mi?
                                    valid_elements.append(elem)
                            except:
                                pass
                        
                        if len(valid_elements) > 5:  # Yeterince yorum bulduk mu?
                            review_elements = valid_elements
                            break
                except Exception as e:
                    print(f"Yorum elementleri aranırken hata: {e}")
            
            # Debug için HTML kaydı
            try:
                html_content = page.content()
                with open(os.path.join(folder_path, "page_source.html"), "w", encoding="utf-8") as f:
                    f.write(html_content)
                print("Sayfa kaynağı kaydedildi")
            except Exception as e:
                print(f"Sayfa kaynağı kaydedilemedi: {e}")
            
            print(f"İşlenecek {len(review_elements)} yorum elementi bulundu")
            counter = 0
            
            # Her bir yorum için işlem yap
            for review in review_elements:
                try:
                    # Önce yorum metnini bul
                    review_text = ""
                    for text_selector in ['span', 'div > span', '*[role="text"]', '[jscontroller]']:
                        try:
                            elements = review.locator(text_selector).all()
                            for el in elements:
                                text = el.text_content().strip()
                                if len(text.split()) > 10:  # 10 kelimeden uzun
                                    review_text = text
                                    break
                            if review_text:
                                break
                        except:
                            continue
                    
                    # "Daha fazla" / "More" butonuna tıklayarak tam yorumları görüntüle
                    if review_text:
                        try:
                            # İlk önce yorum içinde "Daha fazla" veya "More" butonu olup olmadığını kontrol et
                            more_buttons = review.locator('button:has-text("Daha fazla"), button:has-text("More"), span:has-text("Daha fazla"), span:has-text("more"), [aria-label="Daha fazla"], [aria-label="More"]').all()
                            if more_buttons:
                                for more_button in more_buttons:
                                    try:
                                        # Butonun görünür olduğundan emin ol
                                        if more_button.is_visible():
                                            # Düğmeye tıkla
                                            more_button.click(timeout=1000)
                                            print(f"'Daha fazla' butonuna tıklandı.")
                                            time.sleep(0.5)  # Yorumun açılması için kısa bir süre bekle
                                            
                                            # Tam metni tekrar al
                                            for text_selector in ['span', 'div > span', '*[role="text"]', '[jscontroller]']:
                                                try:
                                                    elements = review.locator(text_selector).all()
                                                    for el in elements:
                                                        updated_text = el.text_content().strip()
                                                        # Daha uzun ve muhtemelen tam metin mi kontrol et
                                                        if len(updated_text) > len(review_text) and len(updated_text.split()) > 10:
                                                            review_text = updated_text
                                                            print("Tam yorum metni alındı.")
                                                            break
                                                except Exception as exp:
                                                    print(f"Tam metin çekilirken hata: {exp}")
                                            break  # İlk görünür butona tıkladıktan sonra döngüden çık
                                    except Exception as e:
                                        print(f"'Daha fazla' butonuna tıklarken hata: {e}")
                                        continue
                        except Exception as e:
                            print(f"'Daha fazla' butonu aranırken hata: {e}")
                    
                    if not review_text or len(review_text.split()) <= 10:
                        continue
                    
                    # Kullanıcı adını ve bilgilerini daha doğru çek
                    user_info = {
                        'name': "Bilinmeyen Kullanıcı",
                        'is_local_guide': False,
                        'review_count': "",
                        'photos_count': "",
                        'local_guide_level': ""
                    }
                    
                    # ÖNEMLİ: Kullanıcı bloğunu doğru bul
                    user_block = None
                    try:
                        # Kullanıcı bloğu genellikle yorum içindeki ilk link veya belirli sınıfları içeren bir div
                        user_selectors = [
                            "a", 
                            "div.d4r55", 
                            "div[class*='user']", 
                            "div.WNxzHc"
                        ]
                        
                        for selector in user_selectors:
                            elements = review.locator(selector).all()
                            for elem in elements:
                                # Bağlantı varsa ve katkıda bulunan kullanıcı linki ise
                                href = elem.get_attribute("href") or ""
                                content = elem.text_content().strip()
                                
                                if ("contrib" in href or "maps/contrib" in href) and content:
                                    user_block = elem
                                    break
                                    
                                # Link olmayan bir kullanıcı bloğu olabilir
                                if content and len(content) > 2 and len(content) < 50 and "+" not in content:
                                    if not re.search(r'http|www|\.(com|net|org)', content.lower()):
                                        user_block = elem
                                        break
                            
                            if user_block:
                                break
                        
                        # Bulunan bloğun metin içeriğini al
                        if user_block:
                            # Ana kullanıcı ismini al
                            user_text = user_block.text_content().strip()
                            
                            # İsim ve diğer bilgileri ayırmaya çalış
                            if '\n' in user_text:
                                parts = user_text.split('\n')
                                user_info['name'] = parts[0].strip()
                                
                                # Diğer parçalardan yerel rehber ve inceleme sayısı bilgilerini çıkart
                                for part in parts[1:]:
                                    part = part.strip()
                                    if "yerel rehber" in part.lower() or "local guide" in part.lower():
                                        user_info['is_local_guide'] = True
                                        
                                        # Seviye bilgisini çıkart (örn: "Yerel Rehber · Düzey 5")
                                        level_match = re.search(r'düzey\s+(\d+)', part.lower())
                                        if level_match:
                                            user_info['local_guide_level'] = f"Düzey {level_match.group(1)}"
                                        else:
                                            level_match = re.search(r'level\s+(\d+)', part.lower())
                                            if level_match:
                                                user_info['local_guide_level'] = f"Düzey {level_match.group(1)}"
                                    
                                    # İnceleme sayısını çıkart
                                    review_count_match = re.search(r'(\d+)\s*(inceleme|yorum|değerlendirme|review)', part.lower())
                                    if review_count_match:
                                        user_info['review_count'] = f"{review_count_match.group(1)} inceleme"
                                    
                                    # Fotoğraf sayısını çıkart
                                    photo_count_match = re.search(r'(\d+)\s*(fotoğraf|photo)', part.lower())
                                    if photo_count_match:
                                        user_info['photos_count'] = f"{photo_count_match.group(1)} fotoğraf"
                            else:
                                # Tek satır varsa sadece isim olarak kaydet
                                user_info['name'] = user_text
                            
                            # Yerel rehber bilgisini ayrıca kontrol et
                            if not user_info['is_local_guide']:
                                # Ana kullanıcı bloğunun yakınında "Yerel Rehber" veya "Local Guide" yazısı olabilir
                                guide_element = review.locator('span:has-text("Yerel Rehber"), span:has-text("Local Guide")').first
                                if guide_element:
                                    user_info['is_local_guide'] = True
                            
                            # İnceleme sayısı bilgisini ayrıca kontrol et
                            if not user_info['review_count']:
                                stats_elements = review.locator('span:has-text("inceleme"), span:has-text("review"), span:has-text("yorum")').all()
                                for elem in stats_elements:
                                    text = elem.text_content().strip()
                                    if re.search(r'\d+\s*(inceleme|yorum|değerlendirme|review)', text.lower()):
                                        user_info['review_count'] = text
                                        break
                    except Exception as e:
                        print(f"Kullanıcı bilgileri alınırken hata: {e}")
                    
                    # Kullanıcı ismi boşsa veya çok uzunsa, alternatif yöntemleri dene
                    if not user_info['name'] or len(user_info['name']) > 50 or user_info['name'] == "Bilinmeyen Kullanıcı":
                        for name_selector in ['div.d4r55', 'a', 'div > a', 'div[class*="user"]', 'div[class*="name"]']:
                            try:
                                elements = review.locator(name_selector).all()
                                for el in elements:
                                    text = el.text_content().strip()
                                    if text and len(text) > 2 and len(text) < 50 and "+" not in text and "yorum" not in text.lower() and "yıldız" not in text.lower():
                                        user_info['name'] = text
                                        break
                                if user_info['name'] != "Bilinmeyen Kullanıcı":
                                    break
                            except:
                                continue
                    
                    # Yorum tarihini bul
                    review_date = "Belirtilmemiş"
                    for date_selector in [
                        'span.rsqaWe', 
                        'span[class*="date"]', 
                        'span[aria-label*="gün"]', 
                        'span:has-text("ay önce")', 
                        'span:has-text("gün önce")',
                        'span:has-text("hafta önce")', 
                        'span:has-text("week")'
                    ]:
                        try:
                            elements = review.locator(date_selector).all()
                            for el in elements:
                                text = el.text_content().strip()
                                if text and ("gün" in text.lower() or "ay" in text.lower() or "yıl" in text.lower() or 
                                            "hafta" in text.lower() or "week" in text.lower() or 
                                            re.search(r'\d{4}', text)):
                                    review_date = text
                                    break
                            if review_date != "Belirtilmemiş":
                                break
                        except:
                            continue
                    
                    # Tarih belirtilmemişse ve "birkaç hafta önce" tarzında bir şey olabilir
                    if review_date == "Belirtilmemiş":
                        try:
                            # Genel zamana ilişkin metinleri kontrol et
                            time_texts = review.locator('span').all()
                            for el in time_texts:
                                text = el.text_content().strip().lower()
                                if ("önce" in text or "ago" in text) and len(text) < 30:
                                    if any(keyword in text for keyword in ["gün", "ay", "yıl", "hafta", "week", "day", "month", "year"]):
                                        review_date = text
                                        break
                        except:
                            pass
                    
                    # Eğer hala bulunamadıysa ve içerik kısa bir süre önce gönderildiyse, varsayılan bir değer atayabiliriz
                    if review_date == "Belirtilmemiş":
                        review_date = "Yeni yorum"
                    
                    # Puanı bul
                    rating = "Belirtilmemiş"
                    for rating_selector in ['span.kvMYJc', 'span[role="img"]', 'div[role="img"]', 'span[aria-label*="yıldız"]']:
                        try:
                            elements = review.locator(rating_selector).all()
                            for el in elements:
                                try:
                                    # Önce aria-label'dan bak
                                    aria_label = el.get_attribute('aria-label')
                                    if aria_label and ("yıldız" in aria_label.lower() or "star" in aria_label.lower()):
                                        rating = aria_label
                                    break
                                except:
                                    pass
                            if rating != "Belirtilmemiş":
                                break
                        except:
                            continue
                    
                    # Kullanıcı altı açıklama metninden ek bilgileri daha esnek çek
                    review_count = ""
                    photo_count = ""
                    is_local_guide = False
                    try:
                        # Kullanıcı bloğunun hemen altındaki veya yakınındaki tüm metinleri birleştir
                        info_texts = []
                        if user_block:
                            # Kullanıcı bloğunun kardeş veya alt elementlerinde metin ara
                            try:
                                # XPath ile erişim yerine daha güvenli bir yöntem kullanalım
                                parent = user_block.locator('xpath=..').first
                                if parent:
                                    siblings = parent.locator('*').all()
                                    for sib in siblings:
                                        sib_text = sib.text_content().strip()
                                        if sib_text:
                                            info_texts.append(sib_text)
                                # Ayrıca kendi bloğunun içindeki tüm metinleri de ekle
                                block_text = user_block.text_content().strip()
                                if block_text:
                                    info_texts.append(block_text)
                            except Exception as e:
                                print(f"Kullanıcı bloğu işlenirken hata: {e}")
                        
                        # Yedek: Yorum bloğundaki tüm span ve div'lerde de ara
                        for el in review.locator('span, div').all():
                            t = el.text_content().strip()
                            if t and t not in info_texts:
                                info_texts.append(t)
                        # Tüm metinleri birleştir
                        all_info = ' | '.join(info_texts).lower()
                        # Yerel rehber kontrolü
                        if re.search(r'yerel rehber|local guide', all_info):
                            is_local_guide = True
                        # İnceleme/yorum sayısı
                        review_count_match = re.search(r'(\d+)\s*(inceleme|yorum|değerlendirme|review|reviews)', all_info)
                        if review_count_match:
                            review_count = f"{review_count_match.group(1)} inceleme"
                        # Fotoğraf sayısı
                        photo_count_match = re.search(r'(\d+)\s*(fotoğraf|photo|photos)', all_info)
                        if photo_count_match:
                            photo_count = f"{photo_count_match.group(1)} fotoğraf"
                    except Exception as e:
                        print(f"Kullanıcı ek bilgileri alınırken hata: {e}")
                    # Temizlik işlemi: Kullanıcı adını sadeleştir
                    user_name = user_info['name']
                    if len(user_name) > 50:
                        user_name = user_name[:47] + "..."
                    # Veri eklerken filtreleme yapıyoruz - müşteri isteğine göre
                    reviews.append({
                        'Kullanici': user_name,
                        'Tarih': review_date,
                        'Puan': rating,
                        'Yorum': review_text
                    })
                    counter += 1
                    if counter >= max_reviews:
                        break
                except Exception as e:
                    print(f"Yorum işlenirken hata: {e}")
                    continue
            
            print(f"{len(reviews)} yorum başarıyla toplandı.")
            
            # Yorumları kaydet
            if reviews:
                pd.DataFrame(reviews).to_csv(os.path.join(folder_path, 'yorumlar.csv'), index=False)
                print(f"Toplam {len(reviews)} yorum kaydedildi.")
            else:
                empty_reviews = [{
                    'Kullanici': 'Yorum bulunamadı',
                    'Tarih': '',
                    'Puan': '',
                    'Yorum': 'Yorumlar çekilemedi'
                }]
                pd.DataFrame(empty_reviews).to_csv(os.path.join(folder_path, 'yorumlar.csv'), index=False)
                print("Yorum bulunamadı.")
        except Exception as e:
            print(f"Yorumlar toplanırken hata oluştu: {e}")
            empty_reviews = [{
                'Kullanici': 'Hata',
                'Tarih': '',
                'Puan': '',
                'Yorum': f'Hata: {str(e)}'
            }]
            pd.DataFrame(empty_reviews).to_csv(os.path.join(folder_path, 'yorumlar.csv'), index=False)
        
        # Tamamlandı
        try:
            page.screenshot(path=os.path.join(folder_path, "ekran_goruntusu_son.png"), full_page=True)
        except:
            pass
            
        time.sleep(2)
        browser.close()
        print(f"\nTüm veriler {folder_path} klasörüne kaydedildi.")

if __name__ == "__main__":
    url = input("Google Maps mekan bağlantısını girin: ")
    
    # Maksimum yorum sayısını sor (varsayılan 200)
    try:
        max_reviews_input = input("Kaç yorum çekmek istersiniz? (varsayılan: 200): ")
        max_reviews = int(max_reviews_input) if max_reviews_input.strip() else 200
    except:
        max_reviews = 200
    
    # En yeni sıralama kullan
    sort_by = "newest"
    
    scrape_google_maps(url, max_reviews, sort_by)
