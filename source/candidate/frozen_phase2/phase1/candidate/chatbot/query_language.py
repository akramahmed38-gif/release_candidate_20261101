"""Conservative, model-free query normalization; never transliterate arbitrary IDs."""
from functools import lru_cache
import re

# Language spellings only: business facts always come from the learning index.
_GROUPS = {
    'عايز': ('3ayez','3awez','3ayz','ayez','3ayz'),
    'اعرف': ('a3raf','a3rf','aaref'),
    'ايه': ('eh','eih','eihh'),
    'هو': ('howa','hwa','huwa'),
    'هي': ('heya','hya'),
    'ما': ('ma',),
    'ازاي': ('ezay','ezzay','ezai','ezzai'),
    'كام': ('kam','kaam'),
    'امتى': ('emta','imta'),
    'فين': ('feen','fen'),
    'ممكن': ('momken','mumken','momkn'),
    'لو': ('law','lw'),
    'سمحت': ('sama7t','samaht'),
    'انا': ('ana',),
    'مش': ('mesh','msh','mish'),
    'لا': ('la2','laa'),
    'بدون': ('bedoon','bedon','bdoon'),
    'بس': ('bas','bass','bs'),
    'الف': ('alf','alaf'),
    'مليون': ('melyon','million'),
    'مميزات': ('momayezat','momyzat','memayzat','momezat'),
    'مميزاته': ('momayezato','momayezatoh','momyzato'),
    'مزايا': ('mazaya','mzaya'),
    'رسوم': ('rosom','rosoom','rusoom'),
    'رسومه': ('rosomo','rosoomo'),
    'مصاريف': ('masareef','masarif','msareef'),
    'عمولة': ('3omola','3omoola','omola'),
    'شروط': ('shoroot','shorout','shorot','shroot'),
    'متطلبات': ('motatalabat','metatalabat'),
    'خطوات': ('khotwat','5otwat','khatwat'),
    'حد': ('7ad','hadd'),
    'اقصى': ('a2sa','aqsa','aksa'),
    'ادنى': ('adna','adnaa'),
    'سحب': ('sa7b','sa7eb','sahb'),
    'ايداع': ('eeda3','eda3','ida3','eida3'),
    'تحويل': ('ta7weel','tahweel','ta7wil','tahwil'),
    'تحويلات': ('ta7weelat','tahweelat'),
    'تفعيل': ('taf3eel','taf3il','tafeel'),
    'اشتراك': ('eshterak','eshtrak','ishtirak'),
    'مجاني': ('magany','magani','maganiy'),
    'خصم': ('khasm','5asm','khasem'),
    'محفظة': ('ma7faza','ma7fza','mahfaza','ma7fazah'),
    'كارت': ('kart','kارت','cart'),
    'بطاقة': ('beta2a','bita2a','betaqa'),
    'اصفر': ('asfar','a9far'),
    'فوري': ('fawry','fawri'),
    'يومي': ('yomy','youmy','yawmy','yommy'),
    'بلس': ('plus',),
    'حساب': ('7esab','7sab','hesab'),
    'حسابي': ('7esaby','hesaby'),
    'رصيد': ('raseed','rasid'),
    'عميل': ('3ameel','3amil','ameel'),
    'العميل': ('el3ameel','el3amil'),
    'فلوس': ('feloos','flos','felous'),
    'فرع': ('far3','far3a'),
    'فروع': ('foroo3','foro3'),
    'خدمة': ('5edma','khedma','5dma'),
    'خدمات': ('5adamat','khadamat'),
    'مشكلة': ('moshkela','moshkla','mushkila'),
    'خطأ': ('5ata2','khata2'),
    'رفض': ('rafd','rafd'),
    'مرفوض': ('marfood','marfod'),
    'مقفول': ('ma2fool','ma2fol'),
    'الغاء': ('elgha','el8a2','elgha2'),
    'استرداد': ('esterdad','istirdad'),
    'تقسيط': ('ta2seet','ta2sit','taqseet'),
    'دفع': ('daf3','dafaa'),
    'فواتير': ('fawateer','fawatir'),
    'فاتورة': ('fatoora','fatora'),
    'تأمين': ('ta2meen','ta2min'),
    'معنى': ('ma3na','maana'),
    'نطق': ('not2','notq'),
    'نوع': ('no3','noo3'),
    'تصنيف': ('tasneef','tasnif'),
    'شهر': ('shahr','shaher'),
    'يوم': ('yom','youm'),
    'سنة': ('sana','sanah'),
}
FRANCO_WORDS = {spelling:word for word,spellings in _GROUPS.items() for spelling in spellings}
_WEAK = {'ma','eh','eih','howa','hwa','heya','hya','kam','fen','law','lw','ana','bas','bass','bs','alf','plus','fawry','fawri','cart','million','sana','yomy','youmy','yawmy','yommy'}
_WORD = re.compile(r'(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9]*|(?<![A-Za-z0-9_])[2356789][A-Za-z][A-Za-z0-9]*')


def _known(token):
    word=FRANCO_WORDS.get(token)
    if word:return word
    for prefix,arabic in [('el','ال'),('al','ال'),('wel','وال'),('w','و')]:
        if token.startswith(prefix) and token[len(prefix):] in FRANCO_WORDS:
            return arabic+FRANCO_WORDS[token[len(prefix):]]
    return None


@lru_cache(maxsize=4096)
def normalize_franco(question):
    text=str(question or '')
    matches=list(_WORD.finditer(text))
    # A digit-letter mix alone may be a model name, reference, ID or version.
    recognized=[m.group().lower() for m in matches if not m.group().isupper() and _known(m.group().lower())]
    strong=[word for word in recognized if word not in _WEAK]
    if not strong and not any(word in {'eh','eih','howa','hwa','heya','hya'} for word in recognized) and not (recognized and re.search(r'[\u0621-\u064a]',text)):
        return text
    protected=[(m.start(),m.end()) for m in re.finditer(r'https?://\S+|`[^`]+`',text,re.I)]

    def convert(match):
        token=match.group()
        if any(start<=match.start()<end for start,end in protected):return token
        before=match.start()>1 and text[match.start()-1] in '-_./:@' and text[match.start()-2].isascii() and text[match.start()-2].isalnum()
        after=match.end()+1<len(text) and text[match.end()] in '-_./:@' and text[match.end()+1].isascii() and text[match.end()+1].isalnum()
        if before or after:
            return token
        if token.isupper():return token
        return _known(token.lower()) or token

    text=_WORD.sub(convert,text)
    # Standalone articles/conjunctions are converted only in detected Franco.
    text=re.sub(r'\b(?:el|al)\s+(?=[\u0600-\u06ff])','ال',text,flags=re.I)
    text=re.sub(r'\bw\s+(?=[\u0600-\u06ff])','و',text,flags=re.I)
    return text


def reply_language(question):
    text=str(question or '')
    if re.search(r'[\u0600-\u06ff]',text):return 'ar'
    if normalize_franco(text)!=text:return 'ar'
    words=re.findall(r'[A-Za-z]+',text.casefold())
    english={'what','which','when','where','why','how','is','are','does','can','please',
             'fees','benefits','features','requirements','steps','meaning','pronunciation',
             'wallet','withdrawal','deposit','transfer','account','limit','refund','explain'}
    if english.intersection(words):return 'en'
    if any(_known(word) for word in words):return 'ar'
    return 'en' if words else 'ar'


def franco_clarification(question):
    text=str(question or '')
    if normalize_franco(text)==text:return None
    protected=[(m.start(),m.end()) for m in re.finditer(r'https?://\S+|`[^`]+`',text,re.I)]
    for match in _WORD.finditer(text):
        word=match.group()
        if _known(word.lower()) or any(c.isupper() for c in word):continue
        if any(start<=match.start()<end for start,end in protected):continue
        if (match.start() and text[match.start()-1] in '-_./:@') or (match.end()<len(text) and text[match.end()] in '-_./:@'):continue
        if re.search(r'[a-z][2356789][a-z]',word.lower()):
            answer='في كلمة فرانكو مش واضحة. ممكن تعيد كتابة سؤالك بالعربية أو الإنجليزية عشان أجاوبك بدقة؟'
            return {'type':'clarification','answer_type':'clarification','answer':answer,
                    'clarification':{'reason':'unclear_franco','question':answer,'options':[]},
                    'clarification_reason':'unclear_franco','sources':[],'fallback_used':False}
    return None


_ENGLISH_FOLLOWUPS = {
    'what are its benefits':'وما هي مميزاته', 'and its benefits':'وما هي مميزاته',
    'what are its features':'وما هي مميزاته', 'and its features':'وما هي مميزاته',
    'what about the fees':'والرسوم', 'what about its fees':'والرسوم',
    'and the fees':'والرسوم', 'how much does it cost':'رسومه كام',
    'what are its requirements':'وما هي شروطه', 'and its requirements':'وما هي شروطه',
    'what are the steps':'والخطوات', 'and the steps':'والخطوات',
}


def normalize_conversation_query(question):
    text=normalize_franco(question)
    key=re.sub(r'\s+',' ',text).strip().casefold().strip(' ?!.')
    return _ENGLISH_FOLLOWUPS.get(key,text)
