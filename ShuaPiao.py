# -*- coding: utf-8 -*-
#coding:utf-8
"""
 ***All Rights Reserved
 run env: python 2.7
 @author frankiezhu
 @data 20140106
 ***
"""

import sys, os, time, json
import urllib, httplib
import StringIO, gzip
import traceback
import logging
import datetime
import cProfile
import subprocess
import winsound
import xml.etree.ElementTree
from gui.captcha import  show_captcha


CONF_NAME = './my_xml_conf.xml'
MUSIC_NAME = './music.wav'
##############################################Conf#############################
'''
   Config Class
'''
class Config:
    user='invalid'
    passwd='invalid'
    buy_list = []
    ingnore_list = []
    care_seat_types = []
    query_data = []
    passengers = []
    query_sleep_time = float(1)
    max_auto_times = int(0)
    play_music = False
    seat_code_dict =  {
            "yz_num":["1"],
            "rz_num":["2"],
            "yw_num":["3"],
            "rw_num":["4"],
            "gr_num":["6"],
            "tz_num":["P"],
            "wz_num":["1"],
            "ze_num":["O", "8"],
            "zy_num":["M", "7"],
            "swz_num":["9"],
            }
    #清理临时文件，如验证码等
    clean_temp = False

    def __init__(self):
        pass
    
    def read_config(self, file_name):
        if not os.path.exists(file_name):
            logger.error("file %s not exists,using default." % file_name)
            return False
        logger.info("use config file:%s" % file_name)
        tree = xml.etree.ElementTree.ElementTree(file=file_name)
        root = tree.getroot()
        self.user = root.findall('user')[0].text
        self.passwd = root.findall('passwd')[0].text

        str_tmp = root.findall('buy_list')[0].text
        if str_tmp:
           self.buy_list = [x.strip() for x in str_tmp.strip().rstrip(';').split(';')]
        str_tmp = root.findall('ingnore_list')[0].text
        if str_tmp:
           self.ingnore_list = [x.strip() for x in str_tmp.strip().rstrip(';').split(';')]
        str_tmp = root.findall('care_seat_types')[0].text
        if str_tmp:
            self.care_seat_types = [x.strip() for x in str_tmp.strip().rstrip(';').split(';')]

        train_date = root.findall('query_data/train_date')[0].text.strip()
        from_station = root.findall('query_data/from_station')[0].text.strip()
        to_station = root.findall('query_data/to_station')[0].text.strip()
        purpose_codes = root.findall('query_data/purpose_codes')[0].text.strip()
        self.query_data =  [
                ("leftTicketDTO.train_date", train_date),
                ("leftTicketDTO.from_station", from_station),
                ("leftTicketDTO.to_station", to_station),
                ("purpose_codes", purpose_codes),
                ]
        
        for person in root.findall('passengers/person'):
            person_info = {}
            person_info['name'] = person.findall('name')[0].text.strip()
            person_info['id'] = person.findall('id')[0].text.strip()
            person_info['tel'] = ''
            str_tmp = person.findall('tel')[0].text
            if str_tmp:
                person_info['tel'] = person.findall('tel')[0].text.strip()
            self.passengers.append(person_info)
            
        self.query_sleep_time = float(root.findall('query_sleep_time')[0].text.strip())
        self.max_auto_times = int(root.findall('max_auto_times')[0].text.strip())
        tmp = root.findall('play_music')
        if tmp and int(tmp[0].text.strip()):
            self.play_music = True
        return True

    def show_config(self):
        logger.info("########show conf##############")
        logger.info("User:%s" % self.user)
        logger.info("Buy:%s" % self.buy_list)
        logger.info("Ingnore:%s" % self.ingnore_list)
        logger.info("Query data:%s" % repr(self.query_data))
        logger.info("Passengers:%s" % repr(self.passengers))
        logger.info("Passengers:%s" % self.care_seat_types)
        logger.info("Sleep time:%f" % self.query_sleep_time)
        logger.info("Auto OCR: %d" % self.max_auto_times)
        logger.info("Play music: %d" % self.play_music)
        logger.info("End\n")

####################################Global#######################################
g_conf = Config()
logger = logging.getLogger('shuapiao')
g_conn = httplib.HTTPConnection('kyfw.12306.cn', timeout=100)

##############Exception################

class ShuaPiaoException(Exception):
    # Subclasses that define an __init__ must call Exception.__init__
    # or define self.args.  Otherwise, str() will fail.
    pass

class UnFinishedException(ShuaPiaoException):
    pass


#restart conn
def restart_conn(conn):
    logger.error("conneciont error, reconnect")
    conn.close()
    conn = httplib.HTTPConnection('kyfw.12306.cn', timeout=100)
    conn.connect()

#装饰器
def retries(max_tries):
    def dec(func, conn=g_conn, logger=logger):
        def f2(*args, **kwargs):
            tries = range(max_tries)
            tries.reverse()
            for tries_remaining in tries:
                try:
                   return func(*args, **kwargs)
                except httplib.HTTPException as e:
                    restart_conn(conn)
                except UnFinishedException as e:
                    raise e
                except Exception as e:
                    if tries_remaining > 0:
                        logger.error("catch exception, retry for the %d time" % tries_remaining)
                        logger.error(traceback.format_exc())
                    else:
                        raise e
                else:
                    break
        return f2
    return dec

#调用OCR
def call_tesseract(in_file):
    tesseract_exe_name = 'tesseract'
    expect_len = 4
    out_file = "o"
    
    args = [tesseract_exe_name, in_file, out_file]
    proc = subprocess.Popen(args)
    ret = proc.wait()
    if ret != 0:
        logger.error("call tesseract failed:%d" % ret)
        return ''
    out_full = out_file + '.txt'
    f = open(out_full)
    text = f.read()
    f.close()
    if g_conf.clean_temp:
        os.remove(out_full)
    text = text.rstrip('\r\n')
    text = text.replace(" ", "")
    logger.error("auto OCR read rand_code:%s" % text)
    if len(text) != expect_len:
        logger.error("auto OCR read faild:%s, %d" % (text, len(text)))
        return ''
    return text

'''
    HttpAuto
'''
class HttpAuto:
    def __init__(self):

        self.ext_header = {
            "Accept":"*/*",
            "X-Requested-With":"XMLHttpRequest",
            "Referer": "https://kyfw.12306.cn/otn/login/init#",
            "Accept-Language": "zh-cn",
            "Accept-Encoding": "gzip, deflate",
            "Connection":"Keep-Alive",
            "Cache-Control": "no-cache",
            "User-Agent": "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Trident/5.0)",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }

        self.proxy_ext_header = {
            "Accept": "*/*",
            "X-Requested-With":"XMLHttpRequest",
            "Referer": "https://kyfw.12306.cn/otn/login/init#",
            "Accept-Language": "zh-cn",
            "Accept-Encoding": "gzip, deflate",
            "Proxy-Connection": "Keep-Alive",
            "Pragma": "no-cache",
            "User-Agent": "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Trident/5.0)",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        #cockies
        self.sid = ''
        self.sip = ''

        #passenger info to be POST
        self.passengerTicketStr = ''
        self.oldPassengerStr = ''

        #used to POST 
        self.globalRepeatSubmitToken = ''
        self.key_check_isChange = ''
        self.orderId = ''
        self.seat_type = ''
        self.train_location = ''
        
        self.pass_code = 'abcd'
        self.rand_code = 'abcd'

        self.train_buying = ''
        
        return

    def construct_passengerTicketStr(self):
        logger.info("###construct_passengerTicketStr###")
        str1 = ''
        str2 = ''
        for p in g_conf.passengers:
            str1 = str1 + self.seat_type + ',0,1,' + p['name'] + ',1,' + p['id'] + ','+ p['tel']+ ',N_'
            str2 = str2 +  p['name'] + ',1,' + p['id'] + ',1_'
        str1 = str1[:-1]
        self.passengerTicketStr = str1.encode('utf8')
        self.oldPassengerStr = str2.encode('utf8')
        logger.info("new:%s" % self.passengerTicketStr)
        logger.info("old:%s" % self.oldPassengerStr)

    def logout(self):
        url_logout = "https://kyfw.12306.cn/otn/login/loginOut"
        g_conn.request('540', url_logout, headers=self.proxy_ext_header)
        return True
                
    def __del__(self):
        self.logout()
        logger.info("close connnection")
        g_conn.close()
        return

    def update_session_info(self, res):
        logger.info("process header cookie")
        update = False
        for h in res.getheaders():
            if h[0] == "set-cookie":
                l = h[1].split(',')[0].strip()
                if l.startswith('JSESSIONID'):
                    self.sid = l.split(';')[0].strip()
                    update = True
                    logger.info("Update sessionid "+self.sid)
                if l.startswith('BIGipServerotn'):
                    self.sip = l.split(';')[0].strip()
                    update = True
                    logger.info("Update sip:"+self.sip)
                l = h[1].split(',')[1].strip()
                if l.startswith('BIGipServerotn'):
                    self.sip = l.split(';')[0].strip()
                    update = True
                    logger.info("Update sip:"+self.sip)
        return update

    def check_pass_code_common(self, module, rand_method):
        ret = False
        auto_times = g_conf.max_auto_times
        while 1:
            url_pass_code = "https://kyfw.12306.cn/otn/passcodeNew/getPassCodeNew?module=%s&rand=%s" % (module, rand_method)
            logger.info("send getPassCodeNew:%s" % datetime.datetime.now())
            header = ''
            if module == 'login':
                header = self.ext_header
            else:
                header = self.proxy_ext_header

            g_conn.request('GET', url_pass_code, headers=header)
            res = g_conn.getresponse()
            logger.info("recv getPassCodeNew=====>:%s" % datetime.datetime.now())
            if module == 'login':
                self.update_session_info(res)
                self.ext_header["Cookie"] = self.sid+';'+self.sip
            
            #save file  
            pic_type = res.getheader('Content-Type').split(';')[0].split('/')[1]
            data = res.read()
            file_name = "./pass_code.%s" % pic_type
            if pic_type == "json":
                time.sleep(0.5)
                continue
            f = open(file_name, 'wb')
            f.write(data)
            f.close()

            #auto read or manual
            read_pass_code = ''
            if g_conf.max_auto_times > 0:
                auto_times = auto_times - 1
                read_pass_code = call_tesseract(file_name)

            if  read_pass_code == '':
                read_pass_code = show_captcha(os.path.abspath("%s" % file_name))
                if read_pass_code == "no":
                    logger.info("Get A new PassCode")
                    continue
                elif read_pass_code == "quit":
                    logger.info("Quit")
                    break
                logger.info("input:%s" % read_pass_code)
            else:
                logger.info("auto:%s" % read_pass_code)

            if g_conf.clean_temp:
                os.remove(file_name)

            data = []
            if module == 'passenger':
                self.proxy_ext_header["Referer"] = "https://kyfw.12306.cn/otn/confirmPassenger/initDc#nogo"
                self.rand_code = read_pass_code
                data = [
                        ("_json_att", ''),
                        ("rand", rand_method),
                        ("randCode", read_pass_code),
                        ("REPEAT_SUBMIT_TOKEN", self.globalRepeatSubmitToken),
                       ]
            elif module == 'login':
                self.pass_code = read_pass_code
                data = [
                        ("randCode", read_pass_code),
                        ("rand", rand_method)
                       ]
            else:
                pass

            post_data = urllib.urlencode(data)
            logger.info("send checkRandCodeAnsyn=====>:") #% post_data
            
            url_check_rand = "https://kyfw.12306.cn/otn/passcodeNew/checkRandCodeAnsyn"
            g_conn.request('POST', url_check_rand, body=post_data, headers=header)
            res = g_conn.getresponse()
            data = res.read()
            logger.info("recv checkRandCodeAnsyn")
            resp = json.loads(data)
            if resp['data'] != 'Y':
                logger.info("rand code not correct:%s" % resp['data'])
                time.sleep(2)
                continue
            else:
                ret = True
                break
        return ret
        
    @retries(3)
    def check_pass_code(self):
        logger.info("#############################Step1:Passcode#########")
        module = 'login'
        rand_method = 'sjrand'
        return self.check_pass_code_common(module, rand_method)

    @retries(3)
    def check_rand_code(self):
        logger.info("#############################Step8:Randcode#########")
        ret = False
        module = 'passenger'
        rand_method = 'randp'
        return self.check_pass_code_common(module, rand_method)
    
    @retries(3)   
    def loginAysnSuggest(self):
        if not self.check_pass_code():
            return False
        logger.info("#############################Step2:Login#########")
        url_login = "https://kyfw.12306.cn/otn/login/loginAysnSuggest"
        data = [
                ("loginUserDTO.user_name", g_conf.user),
                ("userDTO.password", g_conf.passwd),
                ("randCode", self.pass_code)
               ]
        post_data = urllib.urlencode(data)
        #post_data="loginUserDTO.user_name=frankiezhu%%40foxmail.com&userDTO.password=sky123&randCode=%s" % self.pass_code
        self.proxy_ext_header["Cookie"] = self.sid+';'+self.sip 
        logger.info("send loginAysnSuggest=====>")  #% post_data
        g_conn.request('POST', url_login, body=post_data, headers=self.proxy_ext_header)
        res = g_conn.getresponse()
        logger.info("recv loginAysnSuggest")
        data = res.read()
        res_json = json.loads(data)
        if res_json['status'] != True or not res_json['data'].has_key('loginCheck'):
            logger.error(u"login failed:%s" % ''.join(res_json['messages']))
            return False
        if res_json['data']['loginCheck'] == 'Y':
            logger.info(u"login success")
            return True  
        else:
            logger.error(u"login failed:%s" % res_json['data']['loginCheck'])
            return False
        
    def show_ticket(self, it):
         logger.info(it['station_train_code']+it['from_station_name']+it['to_station_name']+it['start_time']+it['arrive_time']+it['lishi']+  \
              it['swz_num']+it['tz_num']+it['zy_num']+it['ze_num']+it['gr_num']+it['rw_num']+it['yw_num']+it['rz_num']+it['wz_num']+it['canWebBuy'])
         return

    ############
    #retcode: -2 for retry, -1 for error, 0 for success
    ############
    def do_ticket(self, json_data, result, want_special):
        ret = 0
        for item in json_data['data']:
            if item['queryLeftNewDTO']['canWebBuy'] == 'N':
                continue  
            train_code = item['queryLeftNewDTO']['station_train_code']
            if want_special and not train_code in g_conf.buy_list:
                continue
            if train_code in g_conf.ingnore_list:
                continue
            has_ticket = False
            for care_type in g_conf.care_seat_types:
                ticket_left = item['queryLeftNewDTO'][care_type]
                if ticket_left == "--"  or ticket_left == u"无":
                    continue
                if ticket_left == u"有":
                    has_ticket = True
                    break
                elif ticket_left.isdigit() and int(ticket_left) >= len(g_conf.passengers):
                    has_ticket = True
                    break
            if has_ticket:
                result[train_code] = item
        #query return none, retry
        if not len(result):
            return -2
        
        #as the list prority
        if want_special:
            for train_code in g_conf.buy_list:
                if not result.has_key(train_code):
                    continue
                self.buying_train = train_code
                ret = self.buy(result[train_code])
                if ret:
                    break
            if not ret:
                logger.info("Err during buy")
                return -1
            else:
                return 0
        #show all
        for train_code, item in result.items():
            self.show_ticket(item['queryLeftNewDTO'])
        
        #get promote
        cmd = raw_input("input cmd[r(etry)|q(uit)|TicketNumToBuy]:")
        cmd = cmd.strip()
        logger.info("input:%s" % cmd)
        if cmd == "r" or cmd == "retry":
            logger.info("retry")
            return -2
        elif cmd == "q" or cmd == "quit":
            logger.info("quit")
            return 0
        else:
            logger.info("buy ticket:%s" % cmd)
            if not result.has_key(cmd):
                logger.info("invalid input, retry")
                return -2
            self.buying_train = cmd
            ret = self.buy(result[cmd])
            if not ret:
                logger.info("Err during buy")
                return -1
            else:
                return 0
    
    @retries(3)           
    def query(self):
        logger.info("#############################Step3:Query#########")
        self.proxy_ext_header["Referer"] = "https://kyfw.12306.cn/otn/leftTicket/init"
        #new proto queryT 2014-09-12
        url_query = "https://kyfw.12306.cn/otn/leftTicket/query?" + urllib.urlencode(g_conf.query_data)
        logger.info("start query======>%s" % url_query)
        want_special = False
        
        if len(g_conf.buy_list) != 0:
            want_special = True
            logger.info("JUST For:%s" % (','.join(g_conf.buy_list)))
        else:
            logger.info(u"车次 出发->到达 时间:到达 历时 商务座 特等座 一等座 二等座 高级软卧 软卧 硬卧 软座 硬座 无座 其他备注")
        #"https://kyfw.12306.cn/otn/leftTicket/query?leftTicketDTO.train_date=2014-01-04&leftTicketDTO.from_station=SHH&leftTicketDTO.to_station=NJH&purpose_codes=ADULT"
        q_cnt = 0
        while 1:
            q_cnt = q_cnt + 1
            g_conn.request('GET', url_query, headers=self.proxy_ext_header)
            res = g_conn.getresponse()
            data = ''
            if res.getheader('Content-Encoding') == 'gzip':
                tmp = StringIO.StringIO(res.read())
                gzipper = gzip.GzipFile(fileobj=tmp)
                data = gzipper.read()
            else:
                data = res.read()
            res_json = json.loads(data)
            if res_json['status'] != True:
                logger.info("parse json failed! data %s" % data)
                continue
            if not len(res_json['data']):
                logger.info(u"没有查到任何车次，请确认你要查的车次信息")
                continue
            result = {}
            ret = self.do_ticket(res_json, result, want_special)
            if ret == 0:
                break
            elif ret == -2:
                logger.info(u"no ticket, refresh %d times!" % q_cnt)
                time.sleep(g_conf.query_sleep_time)
                continue

        return True

    def update_ticket_info(self, req_json):
        self.key_check_isChange = req_json['key_check_isChange']
        self.leftTicketStr = req_json['leftTicketStr']
        self.train_location = req_json['train_location']
        logger.info("Update key_check_isChange=%s" % self.key_check_isChange)
        new_detail = req_json['queryLeftNewDetailDTO']

        #get proper seat_type
        ok_seat = ''
        is_dongche = False
        if self.buying_train.startswith("D"):
            is_dongche = True

        for seat_type in g_conf.care_seat_types:
            l = seat_type.split('_')
            l[0] = l[0].upper()
            new_type = '_'.join(l)
            logger.info("check left tickets for train:%s, seat_type:%s, num:%s" % (self.buying_train, new_type, new_detail[new_type]))
            if int(new_detail[new_type]) >= len(g_conf.passengers):
                ok_seat = seat_type
                break
            #special_case for dongche
            if is_dongche:
                if seat_type == "td_num":
                    new_type = "TDRZ_num"
                elif seat_type == "ze_num":
                    new_type = "EDRZ_num"
                elif seat_type == "zy_num":
                    new_type = "YDRZ_num"
                logger.info("check left tickets for train:%s, seat_type:%s, num:%s" % (self.buying_train, new_type, new_detail[new_type]))
                if int(new_detail[new_type]) >= len(g_conf.passengers):
                    ok_seat = seat_type
                    break
        if not ok_seat:
            logger.error("No seats on train:%s, detail:%s", self.buying_train, new_detail)
            return False
        
        #get seat code
        ticket_req = req_json['queryLeftTicketRequestDTO']
        seat_codes = list(ticket_req['seat_types'])
        logger.info("ticket seat_codes:%s, ok_seat:%s" % (ticket_req['seat_types'], ok_seat))
        ch = ''
        for ch in seat_codes:
            if ch in g_conf.seat_code_dict[ok_seat]:
                break
        if not ch:
            logger.info("Get seat code failed, %s" % ticket_req['seat_types'])
            return False
        self.seat_type = ch
        logger.info("set seat_code:%s" % ch)
        #ready for passenger str
        self.construct_passengerTicketStr()
        return True
                
    @retries(3)
    def confirmPassenger_get_token(self):
        logger.info("#############################Step6:confirmPassenger_get_token #########")
        url_confirm_passenger = "https://kyfw.12306.cn/otn/confirmPassenger/initDc"
        g_conn.request('GET', url_confirm_passenger, headers=self.proxy_ext_header)
        res = g_conn.getresponse()
        data = res.read()
        
        if res.getheader('Content-Encoding') == 'gzip':
            tmp = StringIO.StringIO(data)
            gzipper = gzip.GzipFile(fileobj=tmp)
            data = gzipper.readlines()
        
        key_find = False
        line_token = ''
        line_request_info = ''
        for line in data:
            if line.startswith(u' var globalRepeatSubmitToken = '.encode("utf8")):
                line_token = line.decode("utf8")
                continue
            elif line.startswith(u'           var ticketInfoForPassengerForm'.encode("utf8")):
                line_request_info = line.decode("utf8")
                key_find = True
                break
        if key_find:
            self.globalRepeatSubmitToken = line_token.split('=')[1].strip()[1:-2]
            logger.info("Update globalRepeatSubmitToken=%s" % self.globalRepeatSubmitToken)
            req_data = line_request_info.split('=')[1].strip()[:-1]
            req_data = req_data.replace("null", "''")
            req_data = req_data.replace("true", "True")
            req_data = req_data.replace("false", "False")
            req_json = eval(req_data)
            return self.update_ticket_info(req_json)
        else:
            logger.error("get globalRepeatSubmitToken failed")
            return False
    
    @retries(3)
    def getQueueCount(self, item):
        logger.info("#############################Step10:getQueueCount #########")
        url_queue_count = "https://kyfw.12306.cn/otn/confirmPassenger/getQueueCount"
        #buy_date = 'Sun Jan 5 00:00:00 UTC+0800 2014'
        tlist = time.ctime().split()
        tlist[3] = '00:00:00'
        tlist.insert(4, 'UTC+0800')
        buy_date  = ' '.join(tlist)
         
        data = [
            ("train_date", buy_date),
            ("train_no", item['queryLeftNewDTO']['train_no']),
            ("stationTrainCode",item['queryLeftNewDTO']['station_train_code']),
            ("seatType", self.seat_type),
            ("fromStationTelecode", item['queryLeftNewDTO']['from_station_telecode']),
            ("toStationTelecode", item['queryLeftNewDTO']['to_station_telecode']),
            ("leftTicket",item['queryLeftNewDTO']['yp_info']),
            ("purpose_codes", "00"),
            ("_json_att", ''),
            ("REPEAT_SUBMIT_TOKEN", self.globalRepeatSubmitToken),
            ]
        post_data = urllib.urlencode(data)
        logger.info("send getQueueCount=====>")  #% post_data
        g_conn.request('POST', url_queue_count, body=post_data, headers=self.proxy_ext_header)
        res = g_conn.getresponse()
        data = res.read()
        res_json = json.loads(data)
        logger.info("recv getQueueCount")
        if res_json['status'] != True:
            logger.error("getQueueCount failed:")
            logger.error(data)          
            return False
        return True

    @retries(3)
    def checkOrderInfo(self):
        logger.info("#############################Step9:checkOrderInfo #########")
        url_check_order = "https://kyfw.12306.cn/otn/confirmPassenger/checkOrderInfo"
        data = [
            ("cancel_flag", "2"),
            ("bed_level_order_num", "000000000000000000000000000000"),
            ("passengerTicketStr", self.passengerTicketStr),
            ("oldPassengerStr", self.oldPassengerStr),
            ("tour_flag","dc"),
            ("randCode",self.rand_code),
            ("_json_att", ''),
            ("REPEAT_SUBMIT_TOKEN", self.globalRepeatSubmitToken),
            ]
        post_data = urllib.urlencode(data)
        logger.info("send checkOrderInfo=====>")
        #logger.info("cancel_flag=2&bed_level_order_num=000000000000000000000000000000&passengerTicketStr=1%2C0%2C1%2C%E6%9C%B1%E5%AD%94%E6%B4%8B%2C1%2C320721198711180812%2C13430680458%2CN&oldPassengerStr=%E6%9C%B1%E5%AD%94%E6%B4%8B%2C1%2C320721198711180812%2C1_&tour_flag=dc&randCode=ewgw&_json_att=&REPEAT_SUBMIT_TOKEN=ad51ea02d933faf91d3d2eaeb5d85b3e"
        g_conn.request('POST', url_check_order, body=post_data, headers=self.proxy_ext_header)
        res = g_conn.getresponse()
        data = res.read()
        res_json = json.loads(data)
        logger.info("recv checkOrderInfo") #% res_json
        if res_json['status'] != True or res_json['data']['submitStatus'] != True:
            logger.error("checkOrderInfo failed")
            logger.error(res_json['data']['errMsg'])
            return False
        return True
    
    @retries(3)
    def checkUser(self):
        logger.info("#############################Step4:checkUser #########")
        url_check_info = "https://kyfw.12306.cn/otn/login/checkUser"
        data = [
                ('_json_att', ''),
                ]
        post_data = urllib.urlencode(data)
        logger.info("send checkUser=====>")  #% post_data
        g_conn.request('POST', url_check_info, body=post_data, headers=self.proxy_ext_header)
        res = g_conn.getresponse()
        data = res.read()
        res_json = json.loads(data)
        logger.info("recv checkUser")
        if not res_json['data'].has_key('flag') or res_json['data']['flag'] != True:
            logger.error("check user failed:")
            logger.error(data)
            return False
        else:
            return True
    
    @retries(3)
    def submitOrderRequest(self, item):
        logger.info("#############################Step5:submitOrderRequest #########")
        url_submit = "https://kyfw.12306.cn/otn/leftTicket/submitOrderRequest"
        post_data = "secretStr=" + item['secretStr']+"&train_date=" \
                    + item['queryLeftNewDTO']['start_train_date'] \
                    + "&back_train_date=" + item['queryLeftNewDTO']['start_train_date'] \
                    + "&tour_flag=dc&purpose_codes=ADULT&query_from_station_name=" \
                    + item['queryLeftNewDTO']['from_station_name'] \
                    + "&query_to_station_name="+item['queryLeftNewDTO']['to_station_name']\
                    + "&undefined"
        logger.info("send submitOrderRequest=====>")  #% post_data
        g_conn.request('POST', url_submit, body=post_data.encode("utf8"), headers=self.proxy_ext_header)
        res = g_conn.getresponse()
        data = res.read()
        res_json = json.loads(data)
        if res_json['status'] != True:
            logger.error("submitOrderRequest failed:")
            logger.error(data)
            sub_str = u"您还有未处理的订单".encode('utf8')
            err_msg = ''.join(res_json['messages']).encode('utf8')
            if sub_str in err_msg:
                raise UnFinishedException
            return False
        else:
            return True
    
    @retries(3)
    def confirmSingleForQueue(self):
        logger.info("#############################Step11:confirmSingleForQueue #########")
        url_check_info = "https://kyfw.12306.cn/otn/confirmPassenger/confirmSingleForQueue"
        data = [
                ('passengerTicketStr', self.passengerTicketStr),
                ("oldPassengerStr", self.oldPassengerStr),
                ('randCode', self.rand_code),
                ('purpose_codes', "00"),
                ('key_check_isChange', self.key_check_isChange),
                ('leftTicketStr', self.leftTicketStr),
                ('train_location', self.train_location),
                ('_json_att', ''),
                ("REPEAT_SUBMIT_TOKEN", self.globalRepeatSubmitToken),
                ]
        post_data = urllib.urlencode(data)
        logger.info("send confirmSingleForQueue=====>")  #% post_data
        g_conn.request('POST', url_check_info, body=post_data, headers=self.proxy_ext_header)
        res = g_conn.getresponse()
        data = res.read()
        res_json = json.loads(data)
        logger.info("recv confirmSingleForQueue")
        if res_json['data'].get('submitStatus') != True:
            logger.error("confirmSingleForQueue failed:")
            logger.error(data)
            return False
        else:
            return True
    
    @retries(5)    
    def queryOrderWaitTime(self):
        logger.info("#############################Step12:queryOrderWaitTime #########")
        url_query_wait = "https://kyfw.12306.cn/otn/confirmPassenger/queryOrderWaitTime?"
        cnt = 0
        while 1: 
            data = [
                    ('random', int(time.time())),
                    ("tourFlag", "dc"),
                    ('_json_att', ''),
                    ("REPEAT_SUBMIT_TOKEN", self.globalRepeatSubmitToken),                       
                    ]
            url_query_wait = url_query_wait + urllib.urlencode(data)
            logger.info("send queryOrderWaitTime:%d=====>" % cnt) #% url
            g_conn.request('GET', url_query_wait, headers=self.proxy_ext_header)
            res = g_conn.getresponse()
            data = res.read()
            res_json = json.loads(data)
            logger.info("recv queryOrderWaitTime")
            cnt = cnt + 1
            if not res_json.has_key('data') or res_json['data']['queryOrderWaitTimeStatus'] != True:
                logger.error("queryOrderWaitTime error:")
                logger.error(data)
                break
            if res_json['data']['waitCount']  == 0:
                self.orderId = res_json['data']['orderId']
                logger.info("Update orderId:%s" % self.orderId)
                break
            else:
                continue
        return True

    @retries(3)
    def resultOrderForDcQueue(self):
        logger.info("#############################Step13:resultOrderForDcQueue #########")
        url_result = "https://kyfw.12306.cn/otn/confirmPassenger/resultOrderForDcQueue"
        data = [
                ('orderSequence_no', self.orderId),
                ('_json_att', ''),
                ("REPEAT_SUBMIT_TOKEN", self.globalRepeatSubmitToken),                       
                ]
        post_data = urllib.urlencode(data)
        logger.info("send resultOrderForDcQueue=====>") #% url
        g_conn.request('POST', url_result, body=post_data, headers=self.proxy_ext_header)
        res = g_conn.getresponse()
        data = res.read()
        res_json = json.loads(data)
        logger.info("recv resultOrderForDcQueue")
        if res_json['data'].get('submitStatus') != True:
            err_msg = res_json['data']['errMsg'].encode('utf8')
            success_msg = u"网络传输过程中数据丢失，请查看未完成订单，继续支付！".encode('utf8')
            if err_msg == success_msg:
                logger.info(u"买票成功，请去付款!")
                return True
            else:
                logger.info("get result error:")
                logger.info(data)
                return False
        else:
            logger.info("#############################Success check ticket in webbrowser #########")
            return True

    @retries(3)
    def get_passenger_info(self):
        logger.info("#############################Step7:getPassengerDTOs #########")
        url_get_passager_info = "https://kyfw.12306.cn/otn/confirmPassenger/getPassengerDTOs"
        data = [
                ('_json_att', ''),
                ('REPEAT_SUBMIT_TOKEN', self.globalRepeatSubmitToken)
                ]
        post_data = urllib.urlencode(data)
        logger.info("send getPassengerDTOs=====>")  #% post_data
        g_conn.request('POST', url_get_passager_info, body=post_data, headers=self.proxy_ext_header)
        res = g_conn.getresponse()
        data = res.read()
        res_json = json.loads(data)
        logger.info("recv getPassengerDTOs")
        return True
        
    def buy(self, item):
        #Step4
        if not self.checkUser():
            return False
        #Step5
        if not self.submitOrderRequest(item):
            return False
        #Step6
        if not self.confirmPassenger_get_token():
            return False
        self.proxy_ext_header["Referer"] = "https://kyfw.12306.cn/otn/confirmPassenger/initDc#nogo"
        #Step7
            #self.get_passenger_info
        if g_conf.play_music:
            play_music()
        #Step8
        if not self.check_rand_code():
            return False
        #Step9
        if not self.checkOrderInfo():
            return False
        #Step10
        if not self.getQueueCount(item):
            return False
        #Step11
        if not self.confirmSingleForQueue():
            return False
        if not self.queryOrderWaitTime():
            return False
        #Step13
        if not self.resultOrderForDcQueue():
            return False
        return True


def clean_temp_files():
    logger.info("clean_temp_files")
    pass

##############################################test#############################
@retries(3)
def test_retries():
    logger.info("test retries")
    raise NameError#httplib.HTTPException

def test_ocr():
    f_name = "pass_code.jpeg"
    text = call_tesseract(f_name)
    logger.info("read:%s" % text)

@retries(3)
def test_reconnect():
    header = {
        "Accept":"*/*",
        "X-Requested-With":"XMLHttpRequest",
        "Accept-Language": "zh-cn",
        "Accept-Encoding": "gzip, deflate",
        "Connection":"Keep-Alive",
        "Cache-Control": "no-cache",
        "User-Agent": "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Trident/5.0)",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    url = "https://www.baidu.com"
    for i in range(3):
        logger.info("send")
        g_conn.request('GET', url, headers=header)
        res = g_conn.getresponse()
        data = res.read()
        logger.info("send")
        restart_conn(g_conn)

def test_get_svr_ips():
    logger.info("test_get_svr_ips")
    pass

####################################main#######################################

def main(conf_name):
    #set file log
    f_handler = logging.FileHandler('./log.txt')
    f_formatter = logging.Formatter('[%(asctime)s,%(levelname)s,%(filename)s,%(lineno)d]:%(message)s')
    f_handler.setFormatter(f_formatter)
    logger.addHandler(f_handler)
    #console_log
    c_handler = logging.StreamHandler(sys.stdout)
    c_formatter = logging.Formatter('[%(levelname)s,%(filename)s,%(lineno)d]:%(message)s')
    c_handler.setFormatter(c_formatter)
    logger.addHandler(c_handler)
    logger.setLevel(logging.DEBUG)

    try:
        if not g_conf.read_config(conf_name):
            return False
        g_conf.show_config()
    except Exception as e:
        logger.error(u"配置有误!")
        logger.error(traceback.format_exc())
        return False
    

    #test_retries()
    logger.info("connecting......")
    g_conn.connect()


    has_login = False
    ha = ''
    while 1:
        try:
            if not has_login:
                ha = HttpAuto()
                if not ha.loginAysnSuggest():
                    return False
                has_login = True
            ha.query()
        except UnFinishedException as e:
            logger.error(u"未完成的订单，请用浏览器查看！")
        except ValueError as e:
            logger.error(u"可能服务器挂掉，或次连接被封，请重试！")
            ha_login = False
        except Exception as e:
            return False
        finally:
            logger.info("Again!")
            if g_conf.play_music:
                play_music()
            os.system("pause")
    return True

def play_music():
    logger.info("play music, name:%s" % MUSIC_NAME)
    try:
        winsound.PlaySound(MUSIC_NAME, winsound.SND_ASYNC)
    except Exception as e:
        logger.error("play music failed!")

if __name__ == '__main__':
    #test_ocr()
    #test_reconnect()

    if len(sys.argv) > 1:
        CONF_NAME = sys.argv[1]
    main(CONF_NAME)
    os.system("pause")
 
