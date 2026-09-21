import subprocess
import re
import textwrap

from django.urls import reverse
from .django import reverse_man_url
from .encodings import normalize_html_entities, safe_escape_attribute, anchorencode_id, anchorencode_href

__all__ = ["mandoc_convert", "preprocess", "postprocess", "extract_headings", "extract_description", "_replace_section_heading_ids"]

MANDOC_TIMEOUT = 30  # seconds; mandoc has known hangs on certain malformed input

def mandoc_convert(content, output_type, lang=None):
    if output_type == "html":
        url_pattern = reverse_man_url("", "", "%N", "%S", lang, "")
        cmd = ["mandoc", "-T", "html", "-O", "fragment,man={}".format(url_pattern)]
    elif output_type == "txt":
        cmd = ["mandoc", "-T", "utf8"]
    p = subprocess.run(cmd, check=True, input=content, encoding="utf-8",
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        timeout=MANDOC_TIMEOUT)
    assert p.stdout
    return p.stdout

def preprocess(content, content_type):
    """
    Preprocess the raw source of the manual page before passing it to mandoc.
    """
    assert content_type in {"html", "txt"}

    # replace "\-" with "-" in the .SH macro (otherwise mandoc does not
    # create correct self-links for section headings)
    def repl(match):
        heading = match.group("heading").replace(r"\-", "-")
        return f".SH \"{heading}\""
    content = re.sub(r"^\.SH \"(?P<heading>.+)\"$", repl, content, flags=re.MULTILINE)

    if content_type == "html":
        # replace "\X'tty: link" with a placeholder tag that will be changed to a
        # proper HTML tag in the postprocessing step
        # This is because mandoc completely ignores the URL and renders just the
        # label of the link, and also completely messes up in some contexts such
        # as section headings. See the following issue for details:
        # https://gitlab.archlinux.org/archlinux/archmanweb/-/issues/49
        # Details on the macro syntax can be found in grotty(1):
        # https://man.archlinux.org/man/grotty.1
        def repl(match):
            url = match.group("url")
            label = match.group("label")
            return f"<archmanweb-grotty-link href=\"{url}\">{label}</archmanweb-grotty-link>"
        url_pattern = r"(?P<url>https?://[^\s<>&']+(?<=[\w/]))"
        content = re.sub(r"\\X'tty: link " + url_pattern + r"'(?P<label>.+?)\\X'tty: link'", repl, content)

    return content

def _replace_urls_in_plain_text(html):
    def repl_url(match):
        url = match.group("url")
        if not url:
            return match.group(0)
        return f"<a href='{url}'>{url}</a>"

    skip_tags_pattern = r"\<(?P<skip_tag>a|pre)[^>]*\>.*?\</(?P=skip_tag)\>"
    url_pattern = r"(?P<url>https?://[^\s<>&]+(?<=[\w/]))"
    surrounding_tag_begin = r"(?P<tag_begin>\<(?P<tag>b|i|strong|em|mark)[^>]*\>\s*)?"
    surrounding_tag_end = r"(?(tag_begin)\s*\</(?P=tag)\>|)"
    surrounding_angle_begin = r"(?P<angle>&lt;)?"
    surrounding_angle_end = r"(?(angle)&gt;|)"
    html = re.sub(f"{skip_tags_pattern}|{surrounding_angle_begin}{surrounding_tag_begin}{url_pattern}{surrounding_tag_end}{surrounding_angle_end}",
                  repl_url, html, flags=re.DOTALL)

    # if the URL is the only text in <pre> tags, it gets replaced
    html = re.sub(fr"<pre>\s*{url_pattern}\s*</pre>",
                  repl_url, html, flags=re.DOTALL)

    return html

def _replace_section_heading_ids(html):
    """
    Replace IDs for section headings and self-links with something sensible and wiki-compatible

    E.g. mandoc does not strip the "\\&" roff(7) escape, may lead to duplicate underscores,
    and sometimes uses weird encoding for some chars.
    """
    # section ID getter capable of handling duplicate titles
    ids = set()
    def get_id(title):
        base_id = anchorencode_id(title)
        id = base_id
        j = 2
        while id in ids:
            id = base_id + "_" + str(j)
            j += 1
        ids.add(id)
        return id

    def repl_heading(match):
        heading_tag = match.group("heading_tag")
        heading_attributes = match.group("heading_attributes")
        heading_attributes = " ".join(a for a in heading_attributes.split() if not a.startswith("id="))
        inner = match.group("inner").strip()
        m_permalink = re.match(r"^<a class=[\"']permalink[\"'][^>]*>(?P<title>.*?)</a>$", inner, re.DOTALL)
        if m_permalink:
            title = m_permalink.group("title")
        else:
            title = inner
        title_clean = title.replace("\n", " ")
        text_for_id = normalize_html_entities(re.sub(r"<[^>]+>", "", title_clean))
        id = safe_escape_attribute(get_id(text_for_id))
        href = anchorencode_href(id, input_is_already_id=True)
        title_formatted = re.sub(r'(\([A-Za-z0-9 _\-./\'"]+\))', r'<span class="heading-en" dir="ltr">\1</span>', title)
        return f"<{heading_tag} {heading_attributes} id='{id}'><a class='permalink' href='#{href}'>{title_formatted}</a></{heading_tag}>"

    pattern = re.compile(r"\<(?P<heading_tag>h[1-6])(?P<heading_attributes>[^\>]*)\>"
                         r"(?P<inner>.*?)"
                         r"\<\/(?P=heading_tag)\>", re.DOTALL)
    return re.sub(pattern, repl_heading, html)

def postprocess(text, content_type, lang):
    assert content_type in {"html", "txt"}
    if content_type == "html":
        # replace the placeholder for "\X'tty: link" with a proper HTML tag
        # (see the preprocess function for details)
        def repl(match):
            url = match.group("url")
            label = match.group("label")
            # strip useless formatting from the link label
            tag_begin = r"(?P<tag_begin>\<(?P<tag>b|i|strong|em|mark)[^>]*\>\s*)?"
            tag_end = r"(?(tag_begin)\s*\</(?P=tag)\>|)"
            label = re.sub(f"^{tag_begin}(?P<label>.*){tag_end}$", r"\g<label>", label, flags=re.DOTALL)
            return f"<a href=\"{url}\" class=\"archmanweb-grotty-link\">{label}</a>"
        url_pattern = r"(?P<url>https?://[^\s<>&']+(?<=[\w/]))"
        href_pattern = re.escape("href=&quot;") + url_pattern + re.escape("&quot;")
        pattern = re.escape("&lt;archmanweb-grotty-link") + r"\s+" + href_pattern + re.escape("&gt;") + "(?P<label>.+?)" + re.escape("&lt;/archmanweb-grotty-link&gt;")
        text = re.sub(pattern, repl, text, flags=re.DOTALL)

        # replace references with links
        xref_patterns = [
                # section outside the tag
                r"\<(?P<tag>b|i|strong|em|mark)\>"
                r"(?P<man_name>[A-Za-z0-9@._+\-:\[\]]+)"
                r"\<\/\1\>"
                r"\((?P<section>\d[A-Za-z]{,3})\)",
                # section inside the tag
                r"\<(?P<tag>b|i|strong|em|mark)\>"
                r"(?P<man_name>[A-Za-z0-9@._+\-:\[\]]+)"
                r"\((?P<section>\d[A-Za-z]{,3})\)"
                r"\<\/\1\>",
        ]
        for pattern in xref_patterns:
            text = re.sub(pattern,
                          "<a href='" + reverse("index") + "man/" + r"\g<man_name>.\g<section>." + lang +
                                  r"'>\g<man_name>(\g<section>)</a>",
                          text)

        # remove empty block elements
        # (note that inline elements may contain important whitespace, see
        # https://gitlab.archlinux.org/archlinux/archmanweb/-/issues/48)
        text = re.sub(r"\<(?P<tag>p|pre|div|li)[^>]*\>(\s|&nbsp;)*\</(?P=tag)\>\n?", "", text)

        # strip leading and trailing newlines and remove common indentation
        # from the text inside <pre> tags
        _pre_tag_pattern = re.compile(r"\<pre\>(.+?)\</pre\>", flags=re.DOTALL)
        text = _pre_tag_pattern.sub(lambda match: "<pre>" + textwrap.dedent(match.group(1).strip("\n")) + "</pre>", text)

        # remove blank lines with <br/> tags inside <pre> tags
        # see https://gitlab.archlinux.org/archlinux/archmanweb/-/issues/41
        _br_tag_pattern = re.compile(r"^\s*\<br ?/?\>\s*$\n", flags=re.MULTILINE)
        text = _pre_tag_pattern.sub(lambda match: "<pre>" + _br_tag_pattern.sub("", match.group(1)) + "</pre>", text)

        # remove <br/> tags following a <pre> or <div> tag
        text = re.sub(r"(?<=\</(pre|div)\>)\n?<br/>", "", text)

        # replace URLs in plain-text with <a> links
        text = _replace_urls_in_plain_text(text)

        # replace IDs for section headings and self-links with something sensible and wiki-compatible
        text = _replace_section_heading_ids(text)

        if lang == "fa":
            # 1. Wrap option flags (-v, --help, etc.), complete commands with options (e.g. pacman -Su),
            # version/epoch strings (e.g. 2:1.0-1), variable formats (epoch:version-rel), and version specs in <bdi dir="ltr">
            def _isolate_options_in_html(html_str):
                arg_pattern = (
                    r'(?:'
                    r'&(?:quot|apos|#34|#39);[^\n<>]+?&(?:quot|apos|#34|#39);'
                    r'|\"[^\"\n<>]+\"'
                    r'|\x27[^\x27\n<>]+\x27'
                    r'|-{1,2}[a-zA-Z0-9][a-zA-Z0-9_\-]*(?:=[^\s<,]+)?'
                    r'|[a-zA-Z0-9_\/+=~](?:[a-zA-Z0-9_.\/+=~&;]*[a-zA-Z0-9_\/+=~])?'
                    r')'
                )

                cmd_opt_pattern = (
                    r'(?<![A-Za-z0-9_\-])'
                    r'('
                    r'(?:(?:\b[a-zA-Z0-9_+\-.\/]{1,30}\s+){1,3})?'
                    r'-{1,2}[a-zA-Z0-9][a-zA-Z0-9_\-]*(?:=[^\s<,]+)?'
                    r'(?:[ \t]*,[ \t]*-{1,2}[a-zA-Z0-9][a-zA-Z0-9_\-]*(?:=[^\s<,]+)?)*'
                    rf'(?:\s+{arg_pattern})*'
                    r')'
                    r'(?![A-Za-z0-9_])'
                )

                epoch_ver_pattern = r'(\b\d+:\d+(?:\.\d+)*(?:-[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*)?\b)'
                var_format_pattern = r'(\b[a-zA-Z0-9_]+:[a-zA-Z0-9_\-]+(?::[a-zA-Z0-9_\-]+)*\b)'
                pkg_spec_pattern = r'(\b[a-zA-Z0-9_\-+]+(?:&gt;=|&lt;=|>=|<=|=|>|<)[a-zA-Z0-9_.\-+:]+\b)'
                ver_comp_pattern = r'(\b\d+(?:\.\d+)+[a-zA-Z0-9_.-]*[a-zA-Z0-9_]\b|\b\d+(?:\.\d+)+\b)'

                combined_pattern = re.compile(
                    rf'{cmd_opt_pattern}|{epoch_ver_pattern}|{var_format_pattern}|{pkg_spec_pattern}|{ver_comp_pattern}'
                )

                parts = re.split(r'(<[^>]+>)', html_str)
                skip_tag_names = {'bdi', 'code', 'pre'}
                skip_depth = 0
                for i in range(len(parts)):
                    part = parts[i]
                    if part.startswith('<'):
                        m_close = re.match(r'^</([a-zA-Z0-9]+)>', part)
                        m_open = re.match(r'^<([a-zA-Z0-9]+)\b', part)
                        if m_close:
                            tag = m_close.group(1).lower()
                            if tag in skip_tag_names and skip_depth > 0:
                                skip_depth -= 1
                        elif m_open and not part.endswith('/>'):
                            tag = m_open.group(1).lower()
                            if tag in skip_tag_names:
                                skip_depth += 1
                    else:
                        if skip_depth == 0 and part:
                            parts[i] = combined_pattern.sub(lambda m: f'<bdi dir="ltr">{m.group(0)}</bdi>', part)
                return ''.join(parts)

            text = _isolate_options_in_html(text)

            # 2. Fix NAME section dash directionality
            text = re.sub(
                r'(<section class="Sh"[^>]*>\s*<h1 class="Sh"[^>]*>(?:نام|NAME|&#x0646;&#x0627;&#x0645;).*?</h1>\s*<p class="Pp">\s*)([a-zA-Z0-9_.\-+, <>/b]+?)(\s*-\s*)(?!&rlm;)([؀-ۿ]|&#x06[0-9a-fA-F]{2};)',
                r'\g<1><bdi dir="ltr">\g<2></bdi>\g<3>&rlm;\g<4>',
                text,
                flags=re.DOTALL | re.IGNORECASE
            )

            # 3. Isolate brackets and enforce LTR on SYNOPSIS
            def _isolate_synopsis(match):
                sec = match.group(0)
                if '<section class="Sh" dir="ltr"' not in sec:
                    sec = re.sub(r'<section class="Sh"', '<section class="Sh" dir="ltr"', sec, count=1)
                return sec

            text = re.sub(
                r'<section class="Sh"[^>]*>(?:(?!</section>)[\s\S])*?(?:خلاصه|SYNOPSIS)[\s\S]*?</section>',
                _isolate_synopsis,
                text,
                flags=re.IGNORECASE
            )

            # 4. Prevent English parenthetical phrase splitting across lines and bidi flip
            def _fix_mixed_parenthetical(html_str):
                def repl_parenthetical(m):
                    before = m.group(1)
                    en_part = m.group(2).strip()
                    dash = m.group(3)
                    fa_part = m.group(4).strip()
                    en_nobrk = re.sub(r'\s+', '&nbsp;', en_part)
                    return f'{before}<bdi dir="ltr">{en_nobrk}</bdi> &rlm;- {fa_part}'

                pattern = re.compile(
                    r'(\()((?:<[^>]+>)*[A-Za-z]+(?:<[^>]+>)*(?:\s+[A-Za-z]+)+)(\s*-\s*)((?:[؀-ۿ]|&#x[0-9a-fA-F]+;|\s)+?\))',
                    re.DOTALL
                )
                return pattern.sub(repl_parenthetical, html_str)

            text = _fix_mixed_parenthetical(text)

            # 5. Isolate parentheticals in table.head
            text = re.sub(
                r'(<td class="head-vol"[^>]*>.*?)\(([A-Za-z0-9 _\-./\'"]+)\)(.*?</td>)',
                r'\1<span class="heading-en" dir="ltr">(\2)</span>\3',
                text,
                flags=re.DOTALL
            )

        return text

    elif content_type == "txt":
        # strip mandoc's back-spaced encoding
        return re.sub(".\b", "", text, flags=re.DOTALL)

def extract_headings(html):
    def normalize(title):
        return re.sub(r"\s+", " ", title).strip()
    result = []
    headings_pattern = re.compile(
        r"\<h1(?P<attrs>[^\>]*)\>"
        r"(?P<inner>.*?)"
        r"\<\/h1\>",
        re.DOTALL
    )
    for match in headings_pattern.finditer(html):
        attrs = match.group("attrs")
        inner = match.group("inner").strip()
        m_link = re.search(r"<a class=[\"']permalink[\"'] href=[\"']#(?P<id>[^\"']+)[\"']>(?P<title>.*?)</a>", inner, re.DOTALL)
        if m_link:
            id_val = m_link.group("id")
            raw_title = m_link.group("title")
        else:
            m_id = re.search(r"id=[\"']([^\"']+)[\"']", attrs)
            raw_title = inner
            if m_id:
                id_val = m_id.group(1)
            else:
                text_clean = re.sub(r"<[^>]+>", "", raw_title)
                id_val = anchorencode_id(normalize_html_entities(text_clean))
        clean_title = re.sub(r"<[^>]+>", "", raw_title)
        id_str = normalize_html_entities(id_val)
        title_str = normalize_html_entities(normalize(clean_title))
        if title_str:
            title_display = re.sub(r'(\([A-Za-z0-9 _\-./\'"]+\))', r'<span class="heading-en" dir="ltr">\1</span>', title_str)
            result.append(dict(id=id_str, title=title_display))
    return result

def extract_description(text, lang="en"):
    """
    Extracts the "description" from a plain-text version of a manual page.

    The description is taken from the NAME section (or a hard-coded list of
    translations for non-English manuals). At most 2 paragraphs, one of which
    is usually the one-line description of the manual, are taken to keep the
    description short.

    Note that NAME does not have to be the first section, see e.g. syslog.h(0P).
    """
    dictionary = {
        "ar": "الاسم",
        "bn": "নাম",
        "ca": "NOM",
        "cs": "JMÉNO|NÁZEV",
        "da": "NAVN",
        "de": "BEZEICHNUNG",
        "el": "ΌΝΟΜΑ",
        "eo": "NOMO",
        "es": "NOMBRE",
        "et": "NIMI",
        "fa": "نام|نام دستور|نام برنامه",
        "fi": "NIMI",
        "fr": "NOM",
        "gl": "NOME",
        "hr": "IME",
        "hu": "NÉV",
        "id": "NAMA",
        "it": "NOME",
        "ja": "名前",
        "ko": "이름",
        "lt": "PAVADINIMAS",
        "nb": "NAVN",
        "nl": "NAAM",
        "pl": "NAZWA",
        "pt": "NOME",
        "ro": "NUME",
        "ru": "ИМЯ|НАЗВАНИЕ",
        "sk": "NÁZOV",
        "sl": "IME",
        "sr": "НАЗИВ|ИМЕ|IME",
        "sv": "NAMN",
        "ta": "பெயர்",
        "tr": "İSİM|AD",
        "uk": "НАЗВА|НОМИ|NOMI",
        "vi": "TÊN",
        "zh": "名称|名字|名称|名稱",
    }
    lang = lang.split("_")[0].split("@")[0]
    name = dictionary.get(lang, "NAME")
    if name != "NAME":
        name = "NAME|" + name
    match = re.search(rf"(^{name}$)(?P<description>.+?)(?=^\S)", text, flags=re.MULTILINE | re.DOTALL | re.IGNORECASE)
    if match is None:
        return None
    description = match.group("description")
    description = textwrap.dedent(description.strip("\n"))
    # keep max 2 paragraphs separated by a blank line
    # (some pages contain a lot of text in the NAME section, e.g. owncloud(1) or qwtlicense(3))
    description = "\n\n".join(description.split("\n\n")[:2])
    return description
