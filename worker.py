from pyvirtualdisplay import Display

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.alert import Alert
from selenium.common.exceptions import TimeoutException, UnexpectedAlertPresentException, StaleElementReferenceException
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities


import time as time_

from bs4 import BeautifulSoup

import sys  #for exit()
import codecs

import re

import urllib2

import traceback

import ssdeep
import similarity

from multiprocessing import Pool, Process, Queue, Pipe, Lock
from Queue import Empty



def multiset(list_):

    return set(map(lambda x: (list_.count(x), x), set(list_)))


def list_(multiset):

    return [m for c, m in multiset for i in range(0, c)]

#sys.stdout = codecs.getwriter('utf-8')(sys.stdout)  #needed for printing Unicode in file

display = None
browser = None
f = None

def init():
    global display, browser, f

    display = Display(visible=0, size=(800, 600))
    display.start()

    #Do not load images and use disk cache
    chromeOptions = webdriver.ChromeOptions()
    prefs={"profile.managed_default_content_settings.images": 2, 'disk-cache-size': 4096 }
    chromeOptions.add_experimental_option('prefs', prefs)
    browser = webdriver.Chrome('/home/marko/workspace/chromedriver', chrome_options=chromeOptions)

    #browser = webdriver.Chrome('/home/marko/workspace/chromedriver')
    browser.set_page_load_timeout(20)

    f = open("scan.log", "a")

worker = None
_lock = None

def printing(message):
    global worker, _lock

    _lock.acquire()
    f.write("WORKER %s: %s" % (worker, message))
    f.flush()
    _lock.release()

class Stale():
    pass

STALE = Stale()
ALERT_CONFIRMS = 10

def visible(element):
    if element.parent.name in ['style', 'script', '[document]', 'head']:
        return False
    elif re.match('<!--.*-->', element):
        return False
    elif element.strip() == '':
        return False
    else:
        return True


#Function enables recovery if element disappears from DOM tree or page is refreshed

def getDynamicElements(getFunction, *args):

    try:
        return getFunction(*args)
    except StaleElementReferenceException as e:
        #print "stalan element"
        return STALE
 

#Discards None or anything shorter than three symbols

def filterValidElements(elements):

    for key in elements:

        elements[key] = filter(lambda x: False if x == None or x == STALE or len(x) < 3 else True, elements[key])

    return elements


    allElems = {'alerts': [], 'texts': [], 'images': [], 'backgroundImages': [], 'music': []}


#TODO: Replace with resource and hash!!
def calculateFuzzy(elements):
    #print "**********************************************************************************************\n"
    #print elements

    pics = {}
    for key, value in elements.iteritems():

        if key in ('images', 'backgroundImages'):

            for url in value:
                try:
                    if not url in pics:
                        pic = urllib2.urlopen(url).read()
                        pics[url] = pic
                except (urllib2.HTTPError, urllib2.URLError) as e:
                    printing("Not able to download image: %s\n" % (url, ))
                    pics[url] = None
                except ValueError as e:
                    if 'unknown url type' in str(e):
                        printing("Incorrectly formatted URL.\n")
                        pics[url] = None
                    else:
                        raise e

            elements[key] = filter(lambda (x, y, z): not y == None, \
                            map(  lambda x: (None, None, x) if pics[x] == None else (pics[x], ssdeep.hash(pics[x]), x) , value))

        elif key in ('alerts', 'texts'):

            elements[key] = map(  lambda x: (x, ssdeep.hash(x.encode('utf-8')), None) , value)

        else:   #music

            elements[key] = map(lambda x: (x.split(u'?')[0], ssdeep.hash(x.split(u'?')[0]), x), value) 

    return elements



def getElementContent(allElems):

    #downloading images and backgroundImages
    return allElems


def getElements(mirrorsrc):

    #creating dictionary of Elements
    allElems = {'alerts': [], 'texts': [], 'images': [], 'backgroundImages': [], 'music': []}

    try:
        
        if mirrorsrc[0:7] == 'http://' or mirrorsrc[0:8] == 'https://':
            browser.get(mirrorsrc)
        else:
            browser.get('http://' + mirrorsrc)

        for i in range(0, ALERT_CONFIRMS + 1):       #number of alert confirms: 10 alerts and content

            try:

                try:
                    WebDriverWait(browser, 10).until(
                                EC.presence_of_element_located((By.TAG_NAME, "body"))
                                )
                except TimeoutException as e:
                    printing("Time elapsed for page processing in getElements: %s\n" % mirrorsrc)
                    break
                else:
                    time_.sleep(2)  #safety hold in case HTML is not fully loaded, and time for potential another alert

                    soup = BeautifulSoup(browser.page_source, 'html.parser')

                    #Downloading all element types
                    #All visible text
                    texts = soup.findAll(text=True)
                    visible_texts = filter(visible, texts)  
                    allElems['texts'] = visible_texts

                    #Images (img tags)
                    images = browser.find_elements_by_tag_name('img')
                    images = map(lambda x: getDynamicElements(x.get_attribute, 'src'), images)
                    fimageurls = images

                    allElems['images'] = fimageurls
                    
                    #Background images

                    allNodes = browser.find_elements_by_xpath("//*")

                    allBackImageURLs = map(lambda x: getDynamicElements(x.value_of_css_property, 'background-image'), allNodes)

                    #Although None and STALE are filtered afterwards in filterValidElements
                    allBackImageURLsFiltered = filter(lambda x: False if x in [u'none', u'', None, STALE] else True, allBackImageURLs)

                    allBackImageURLsFiltered = map(lambda x: x[5:-2], allBackImageURLsFiltered)

                    allElems['backgroundImages'] = allBackImageURLsFiltered         #Check for background value is needed as well!!
                    
                    #Music (embed:src, iframe:src,  - width=height=0 does not have to be!!)

                    musicLinks1 = map(lambda x: getDynamicElements(x.get_attribute, 'src'), browser.find_elements_by_tag_name('embed'))
                    musicLinks2 = map(lambda x: getDynamicElements(x.get_attribute, 'src'), browser.find_elements_by_tag_name('iframe'))

                    musicLinks = musicLinks1 + musicLinks2

                    allElems['music'] = musicLinks
                    break


            except UnexpectedAlertPresentException as e:
                printing("Accepting alert in getElements (%s): %s\n" % (mirrorsrc, Alert(browser).text))

                allElems['alerts'].append(Alert(browser).text)
                allElems['texts'] = []
                allElems['images'] = []
                allElems['backgroundImages'] = []
                allElems['music'] = []

                if i == ALERT_CONFIRMS:
                    printing("Too many alerts to confirm, maybe something is not ok (%s).\n%s" % (mirrorsrc, traceback.format_exc()))

                #Accept alert
                Alert(browser).accept()

    except TimeoutException as e:
        #TODO: Replace with signal wait on ITIMER_PROF. That is real timeout we are seeking.
        #Kernel time is important because TCP retransmitions on unreachanble or non-existing webpages.
        #Waiting for the real time as Selenium does is unwanted in multiprocessor environment. Because
        #pseudo concurrency implemented by OS there may be processes waiting to run, so real time will
        #give wrong idea about webpage response time.
        printing("Timeout on page loading in getElements: %s\n" % mirrorsrc)
    except:
        printing("Unsuccessful processing in getElements (%s).\n%s" % (mirrorsrc, traceback.format_exc()))
    finally:
        browser.delete_all_cookies()
        browser.execute_script("return window.stop")
        

    allElemsWithContent = getElementContent(allElems)
    
    return allElemsWithContent



def processWebpage(mirrorsrc):

    elementsOutput = []

    elements = getElements(mirrorsrc)

    elements = filterValidElements(elements)

    elements = calculateFuzzy(elements)

    dataType = lambda basictype, size: 'L' + basictype if size <= 1000 else 'H' + basictype

    for key, values in elements.iteritems():

        for value in values:

            data = bytearray(value[0], 'utf-8') if isinstance(value[0], unicode) else bytearray(value[0])

            elementsOutput.append((dataType(key, len(data)), buffer(data))) 

    return elementsOutput


def serializeElements(mset):

    list_ = sorted(list(mset), key=lambda x: str(x[1][1]))

    return ''.join([str(i[1][1]) * i[0] for i in list_])


maxSim = 0

def calculus(matchesTable, forbbidenList, currSum):

    global maxSim

    if matchesTable == []:

        if currSum > maxSim:

            maxSim = currSum

        return

    for i in range(0, len(matchesTable[0])):

        if i in forbbidenList:
            continue

        calculus(matchesTable[1:], forbbidenList + [i], currSum + matchesTable[0][i])

        


def similarityIndex(elementsWebpage, sdefaces):

    matchesTable = []
    mSum = 0

    #print "length"
    #print len(elementsWebpage), len(sdefaces)

    for i in sdefaces:
        matchesTable.append([])
        for j in elementsWebpage:
            a = ssdeep.hash(i)
            b = ssdeep.hash(j)
            matchesTable[-1].append(spamsum.match(a, b))

    if len(sdefaces) > len(elementsWebpage):

        #iters = itertools.combinations(range(0, len(sdefaces)), len(elementsWebpage))

        for i in range(0, 10):

            s = random.sample(range(0, len(sdefaces)), len(elementsWebpage))

            matchesTableP = map(lambda x: matchesTable[x], s)

            maxSim = 0
            calculus(matchesTableP, [], 0)

            if maxSim > mSum:
                mSum = maxSim
    else:
        maxSim = 0
        #print matchesTable
        calculus(matchesTable, [], 0)
        mSum = maxSim


    return mSum*1.0/len(sdefaces)
            

#greedy
def simindex(sign, web, size):

    if size == 'H':
        sign1 = map(lambda x: ssdeep.hash(str(x)), sign)
        web1 = map(lambda x: ssdeep.hash(str(x)), web)
    else:
        sign1 = map(lambda x: str(x), sign)
        web1 = map(lambda x: str(x), web)

    table = []

    for s in sign1:

        table.append(map(lambda x: similarity.compare(x, s), web1))

    if len(web1) < len(sign1):

        table = map(lambda x: x + [0] * (len(sign1) - len(web1)), table)

    maxi = 0
    for t in range(0, len(table)):

        #print map(lambda x: len(x), table)
        m = max(table[t])
        maxi += m
        i = table[t].index(m)

        for k in range(t+1, len(table)):
            
            del table[k][i]

    return maxi*1.0/len(sign)
            

def match(sign, web):

    sumi = 0

    for k in sign.keys():
    
        if k in web:

            if k[0] == 'L':
                n = simindex(sign[k], web[k], 'L')
            else:
                n = simindex(sign[k], web[k], 'H')

        else:

            n = 0

        sumi += n

    return sumi*1.0/len(sign)


#CRAWLING
def processDomainsList(domains, table):

    elemTypes = ['Lalerts', 'Ltexts', 'Limages', 'LbackgroundImages', 'Lmusic', 'Halerts', 'Htexts', 'Himages', 'HbackgroundImages', 'Hmusic']

    t2=[]

    for t in table:
        elemDict = {}
        for elemType in elemTypes:
            
            p = map(lambda x: x[1], filter(lambda x: str(x[0]) == elemType, t[3]))
            if p:
                elemDict[elemType] = p

        t2.append((t[0], t[1], t[2], elemDict))            


    try:
            
        while True:

             domain = domains.get(False)

             #TODO: map from domain to webpage URL. Is it needed?
             elementsWebpage = processWebpage(domain)
             #elementsWebpage = multiset(elementsWebpage)
             #print "--------------------------------------elementsWebpage-----------------------------------------------------------------"
             #print elementsWebpage

             #elementsWebpage = spamsum.spamsum(serializeElements(elementsWebpage))

             allElems = {'alerts': [], 'texts': [], 'images': [], 'backgroundImages': [], 'music': []}
             allElems = {'alerts': [], 'texts': [], 'images': [], 'backgroundImages': [], 'music': []}
                
             elemsWebpage = {}
             for elemType in elemTypes:
                 p = map(lambda x: x[1], filter(lambda x: x[0] == elemType, elementsWebpage))

                 if p:
                    elemsWebpage[elemType] = p

                
             maxN = -1
             signMax = []
             for sign in t2:

                N = match(sign[3], elemsWebpage)

                if N > maxN:
                    maxN = N
                    signMax = sign[0:3]

             if maxN >= 0.75:
                 printing("Defacement found at %s -> Notifier: %s, Signature ID: %s, Detected on: %s (%s%%)\n" % \
                                            (domain.strip(), signMax[0], signMax[2], signMax[1], maxN*100))
             else:
                 printing("No defacement found (%s)\n" % (domain.strip(), ))

    except Empty:

        pass


def main(defaceSignatures, pipe_child_conn, lock, queues, workerNum):
    global worker, _lock

    init()

    #Must be set up before using printing function
    worker = workerNum
    _lock = lock
    
    #Piping protocol
    while True:

        try:

            ins = pipe_child_conn.recv()

            if ins[0] == 'TAKE':

                queueNum = ins[1]

                printing("Taking queue %s.\n" % (queueNum, ))

                processDomainsList(queues[queueNum], defaceSignatures)

                printing("Successfully done. Queue %s empty.\n" % (queueNum, ))

                pipe_child_conn.send(['DONE', None])

            elif ins[0] == 'DIE':

                printing("Dead.\n")

                browser.quit()
                f.close()

                return 0    # exit from process

        except:
            #In case this section is executed in single-threaded version of tool
            #process would exit. In this case process will wait on pipe for new
            #instruction, and potentialy many domains skipped in processing.
            #Logs should be carefully monitored because execution
            #of 'Unsuccessfully done' section points to bug (potentially unrecoverable).

            pipe_child_conn.send(['DONE', None])

            queueNum = ins[1]

            printing("Unsuccessfully done. Queue %s may not be empty.\n%s\n" % (queueNum, traceback.format_exc()))
        finally:
            #browser.quit() #as process will continue we will not shut down browser
            pass

            



