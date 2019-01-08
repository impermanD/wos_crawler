# -*- coding: utf-8 -*-
import scrapy
import re
from scrapy.http import Request
from scrapy.http import FormRequest
import time
from bs4 import BeautifulSoup
import os


class WosJournalSpiderSpider(scrapy.Spider):
    name = 'wos_journal_spider'
    allowed_domains = ['webofknowledge.com']
    start_urls = ['http://www.webofknowledge.com']

    #提取URL中的SID和QID所需要的正则表达式
    sid_pattern = r'SID=(\w+)&'
    qid_pattern = r'qid=(\d+)&'

    #待爬取期刊列表和列表存放的位置
    JOURNAL_LIST = []
    JOURNAL_LIST_PATH = r'C:\Users\Tom\PycharmProjects\wos_crawler\wos_crawler\input\journal_list.txt'

    #在爬虫运行后进行一次期刊列表的初始化工作，将文件中的期刊名读入
    def start_requests(self):
        with open(self.JOURNAL_LIST_PATH) as file:
            for row in file:
                self.JOURNAL_LIST.append(row.strip().replace('\n',''))
        self.JOURNAL_LIST.sort()

        for url in self.start_urls:
            yield Request(url, dont_filter=True)

    def parse(self, response):
        """
        获取SID并提交高级搜索请求，将高级搜索请求返回给parse_result_entry处理
        每次搜索都更换一次SID

        :param response:
        :return:
        """
        if len(self.JOURNAL_LIST) <= 0:
            print('**待爬取期刊列表为空，不再产生新的异步请求，请等待现有的请求执行完成**')
            return

        #获得当前要爬取的期刊名称
        journal_name = self.JOURNAL_LIST.pop(0)

        #获取SID
        pattern = re.compile(self.sid_pattern)
        result = re.search(pattern, response.url)
        if result is not None:
            sid = result.group(1)
            print('{} 提取得到SID：'.format(journal_name), result.group(1))
        else:
            print('{} SID提取失败'.format(journal_name))
            sid = None
            exit(-1)

        # 提交post高级搜索请求
        adv_search_url = 'http://apps.webofknowledge.com/WOS_AdvancedSearch.do'
        #检索式，目前设定为期刊，稍作修改可以爬取任意检索式
        query = 'SO={} AND PY=(1900-2016)'.format(journal_name.upper())

        query_form = {
            "product": "WOS",
            "search_mode": "AdvancedSearch",
            "SID": sid,
            "input_invalid_notice": "Search Error: Please enter a search term.",
            "input_invalid_notice_limits": " <br/>Note: Fields displayed in scrolling boxes must be combined with at least one other search field.",
            "action": "search",
            "replaceSetId": "",
            "goToPageLoc": "SearchHistoryTableBanner",
            "value(input1)": query,
            "value(searchOp)": "search",
            "value(select2)": "LA",
            "value(input2)": "",
            "value(select3)": "DT",
            "value(input3)": "Article",
            "value(limitCount)": "14",
            "limitStatus": "collapsed",
            "ss_lemmatization": "On",
            "ss_spellchecking": "Suggest",
            "SinceLastVisit_UTC": "",
            "SinceLastVisit_DATE": "",
            "period": "Range Selection",
            "range": "ALL",
            "startYear": "1900",
            "endYear": "2018",
            "editions": ["SCI", "SSCI", "AHCI", "ISTP", "ISSHP", "ESCI", "CCR", "IC"],
            "update_back2search_link_param": "yes",
            "ss_query_language": "",
            "rs_sort_by": "PY.D;LD.D;SO.A;VL.D;PG.A;AU.A",
        }

        #将这一个高级搜索请求yield给parse_result_entry，内容为检索历史记录，包含检索结果的入口
        #同时通过meta参数为下一个处理函数传递sid、journal_name等有用信息
        yield FormRequest(adv_search_url, method='POST', formdata=query_form, dont_filter=True,
                          callback=self.parse_result_entry,
                          meta={'sid': sid, 'journal_name': journal_name, 'query': query})

        #一个检索式爬取完成后，yield一个新的Request，相当于一个尾递归实现的循环功能，
        #好处是每个检索式都是用不同的SID来爬取的
        yield Request(self.start_urls[0], callback=self.parse, dont_filter=True, meta={})

    def parse_result_entry(self, response):
        """
        找到高级检索结果入口链接，交给parse_results处理
        同时还要记录下QID
        :param response:
        :return:
        """
        sid = response.meta['sid']
        journal_name = response.meta['journal_name']
        query = response.meta['query']

        # filename = 'test/result-entry' + str(time.time()) + '-' + sid + '.html'
        # os.makedirs(os.path.dirname(filename), exist_ok=True)
        # with open(filename, 'w', encoding='utf-8') as file:
        #     file.write(response.text)

        #通过bs4解析html找到检索结果的入口
        soup = BeautifulSoup(response.text, 'lxml')
        entry_url = soup.find('a', attrs={'title': 'Click to view the results'}).get('href')
        entry_url = 'http://apps.webofknowledge.com' + entry_url

        #找到入口url中的QID，存放起来以供下一步处理函数使用
        pattern = re.compile(self.qid_pattern)
        result = re.search(pattern, entry_url)
        if result is not None:
            qid = result.group(1)
            print('{} 提取得到qid：'.format(journal_name), result.group(1))
        else:
            print('{} qid提取失败'.format(journal_name))
            exit(-1)

        #yield一个Request给parse_result，让它去处理搜索结果页面，同时用meta传递有用参数
        yield Request(entry_url, callback=self.parse_results,
                      meta={'sid': sid, 'journal_name': journal_name, 'query': query, 'qid': qid})

    def parse_results(self, response):
        sid = response.meta['sid']
        journal_name = response.meta['journal_name']
        query = response.meta['query']
        qid = response.meta['qid']

        # filename = 'test/results-' + str(time.time()) + '-' + sid + '.html'
        # os.makedirs(os.path.dirname(filename), exist_ok=True)
        # with open(filename, 'w', encoding='utf-8') as file:
        #     file.write(response.text)

        #通过bs4获取页面结果数字，得到需要分批爬取的批次数
        soup = BeautifulSoup(response.text, 'lxml')
        paper_num = int(soup.find('span', attrs={'id': 'footer_formatted_count'}).get_text().replace(',', ''))
        span = 500
        iter_num = paper_num // span + 1

        #对每一批次的结果进行导出（500一批）
        for i in range(1, iter_num + 1):
            end = i * span
            start = (i - 1) * span + 1
            if end > paper_num:
                end = paper_num
            print('正在下载 {} 的第 {} 到第 {} 条文献'.format(journal_name, start, end))
            output_form = {
                "selectedIds": "",
                "displayCitedRefs": "true",
                "displayTimesCited": "true",
                "displayUsageInfo": "true",
                "viewType": "summary",
                "product": "WOS",
                "rurl": response.url,
                "mark_id": "WOS",
                "colName": "WOS",
                "search_mode": "AdvancedSearch",
                "locale": "en_US",
                "view_name": "WOS-summary",
                "sortBy": "PY.D;LD.D;SO.A;VL.D;PG.A;AU.A",
                "mode": "OpenOutputService",
                "qid": str(qid),
                "SID": str(sid),
                "format": "saveToFile",
                "filters": "HIGHLY_CITED HOT_PAPER OPEN_ACCESS PMID USAGEIND AUTHORSIDENTIFIERS ACCESSION_NUM FUNDING SUBJECT_CATEGORY JCR_CATEGORY LANG IDS PAGEC SABBR CITREFC ISSN PUBINFO KEYWORDS CITTIMES ADDRS CONFERENCE_SPONSORS DOCTYPE CITREF ABSTRACT CONFERENCE_INFO SOURCE TITLE AUTHORS  ",
                "mark_to": str(end),
                "mark_from": str(start),
                "queryNatural": str(query),
                "count_new_items_marked": "0",
                "use_two_ets": "false",
                "IncitesEntitled": "no",
                "value(record_select_type)": "range",
                "markFrom": str(start),
                "markTo": str(end),
                "fields_selection": "HIGHLY_CITED HOT_PAPER OPEN_ACCESS PMID USAGEIND AUTHORSIDENTIFIERS ACCESSION_NUM FUNDING SUBJECT_CATEGORY JCR_CATEGORY LANG IDS PAGEC SABBR CITREFC ISSN PUBINFO KEYWORDS CITTIMES ADDRS CONFERENCE_SPONSORS DOCTYPE CITREF ABSTRACT CONFERENCE_INFO SOURCE TITLE AUTHORS  ",
                "save_options": "fieldtagged"
            }

            #将下载地址yield一个FormRequest给download_result函数，传递有用参数
            output_url = 'http://apps.webofknowledge.com//OutboundService.do?action=go&&'
            yield FormRequest(output_url, method='POST', formdata=output_form, dont_filter=True,
                               callback=self.download_result,
                               meta={'sid': sid, 'journal_name': journal_name, 'query': query, 'qid': qid,
                                     'start': start, 'end': end})

    def download_result(self, response):
        sid = response.meta['sid']
        journal_name = response.meta['journal_name']
        query = response.meta['query']
        qid = response.meta['qid']
        start = response.meta['start']
        end = response.meta['end']

        #按期刊名称保存文件
        filename = 'output/{}/{}.txt'.format(journal_name, journal_name + '-' + str(start) + '-' + str(end))
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, 'w', encoding='utf-8') as file:
            file.write(response.text)

        print('--成功下载 {} 的第 {} 到第 {} 条文献--'.format(journal_name, start, end))