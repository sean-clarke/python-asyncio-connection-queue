import sys
import os
import time
import datetime
import shutil
import asyncio
import re

# Define Exceptions
class ConnectionError(Exception):
    pass
class LoginError(Exception):
    pass
class PasswordError(Exception):
    pass
class PromptLineError(Exception):
    pass
class IfIndexError(Exception):
    pass
class PortError(Exception):
    pass

# Explanation of variables
# ------------------------
# un : Username
# pw : Password
# nl : New line
# pl : Prompt line
# ip : IP (Device IP)
# rt : Rest Time
# gc : Garbage collector
# sp : Slot-Port pair
# ifin : IfIndex (get if-translate 1-slot-port-0/vdsl)
# q : Queue
# ipi : IP information
# nip : Number of 
# fip : Failed IPs
# cip : Completed IPs
# _??? : Iterable variable, likely a list, generator or collection of ???
# c_??? : Count of variable ???
# t_??? : Temporary container for ???
    
async def connect(ip, ipi):
    """Connects to a single device by given IP, polls device, and logs data"""
#     un = b'USERNAME\n'
#     pw = b'PASSWORD\n'
    nl = b"\n"
    rt = 0.4
    _sp = "unknown"
    # Connect to device
    attempts = 0
    while attempts < 5:
        try:
            if attempts > 0:
                rt *= 1.2
            reader, writer = await asyncio.open_connection(ip, 23)
            await asyncio.sleep(rt)
            gc = await reader.read(32)
            gc = gc.split(b"CONNECTION_PROMPT_SPLIT_STRING")
            if len(gc) != 2 or gc[1] != b"CONNECTION_PROMPT_SPLIT_RESULT":
                raise ConnectionError
            writer.write(un)
            await asyncio.sleep(rt)
            gc = await reader.readline()
            if gc != b"USERNAME\n":
                raise LoginError
            writer.write(pw)
            await asyncio.sleep(rt)
            gc = await reader.readline()
            if gc != b"\rpassword: \n":
                raise PasswordError
        except ConnectionError:
            print("Exception thrown in device with IP: %s" % ip)
            print("Unexpected connection response from device: %s" % ip)
            attempts += 1
            writer.close()
            continue
        except LoginError:
            print("Exception thrown in device with IP: %s" % ip)
            print("Unexpected login response from device: %s" % ip)
            attempts += 1
            writer.close()
            continue
        except PasswordError:
            print("Exception thrown in device with IP: %s" % ip)
            print("Unexpected password response from device: %s" % ip)
            attempts += 1
            writer.close()
            continue
        except Exception as e:
            print("Exception thrown in device with IP: %s" % ip)
            print(e)
            attempts += 1
            continue
        else:
            break
    if attempts > 0:
        print("Attempted to connect to device with ip: %s and failed %s times." % (ip, attempts))
        if attempts >= 5:
            print("Gave up attempting to connect to %s, moving onto next device." % ip)
            ipi['_fip'].append("%s" % ip)
            return
    # Open device log
    dts = str(datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    filename = "VDSLPortStats_%s_%s.log" % (ip, dts)
    log = open(filename, "w+")
    log.write("MXKIP Slot Port AdminStatus OperStatus Mode LineType DnTrain UpTrain MaxDnTrain MaxUpTrain DnSNRMgn UpSNRMgn DnOutPwr UpOutPwr DnLineAtn UpLineAtn UpTime")
    # Get prompt line (pl), check whether it is valid, then start gathering device info
    try:
        writer.write(nl)
        await asyncio.sleep(rt)
        pl = await reader.readline()
        repl = b'\\r[\w*-?#?]*\w*> \\n'
        if not re.search(repl, pl):
            raise PromptLineError
        # Get device info and write to log
        # Get Slots
        if _sp == "unknown":
            writer.write(b"slots\n")
            await asyncio.sleep(rt)
            writer.write(nl)
            await asyncio.sleep(rt)
            _sp = await reader.readuntil(pl)
            _sp = _sp.decode("ascii").split("\n\r")
            _sp = [v for v in _sp if bool(re.search(r"\d+:", v))]
            _sp = [v for v in _sp if (bool(re.search(r" 24 ", v)) or bool(re.search(r" 48 ", v)))]
            _sp = [v for v in _sp if not bool(re.search(r" ULCS/EBS ", v))]
            t_sp = []
            for sp in _sp:
                if bool(re.search(r"\d", sp[0])):
                    sn = sp[:2]
                else:
                    sn = sp[1]
                if bool(re.search(r" 24 ", sp)):
                    sp = sn + ",24"
                    t_sp.append(sp)
                else:
                    sp = sn + ",48"
                    t_sp.append(sp)
            _sp = t_sp
        if _sp == []:
            print("\nDevice with IP: %s has no loggable slots, consider reviewing why it is in list of IPs\n" % ip)
            return
        # For each slot
        for sp in _sp:
            slot, ports = sp.split(",")
            slot = int(slot)
            ports = int(ports)
            ports = [i for i in range(1, ports + 1)]
            pifin = "unknown"
            # For each port
            for port in ports:
                adminstatus = "unknown"
                operstatus = "unknown"
                mode = "unknown"
                linetype = "unknown"
                dntrain = "unknown"
                uptrain = "unknown"
                maxdntrain = "unknown"
                maxuptrain = "unknown"
                dnSNRmgn = "unknown"
                upSNRmgn = "unknown"
                dnoutpwr = "unknown"
                upoutpwr = "unknown"
                dnlineatn = "unknown"
                uplineatn = "unknown"
                uptime = "unknown"
                
                try:
                    # Get ifIndex (ifin)
                    if pifin == "unknown":
                        writer.write(b"get if-translate 1-" + str(slot).encode("ascii") + b"-" + str(port).encode("ascii") + b"-0/vdsl\n")
                        await asyncio.sleep(rt)
                        writer.write(nl)
                        await asyncio.sleep(rt)
                        ifin = await reader.readuntil(pl)
                        ifin = ifin.split(b"\n\r")
                        if len(ifin) != 16:
                            raise IfIndexError
                        ifin = [v for v in ifin if bool(re.search(r"ifIndex:", v.decode("ascii"))) or bool(re.search(r"adminstatus:", v.decode("ascii")))]
                        ifin, adminstatus = ifin[0], ifin[1]
                        gc, ifin = ifin.split(b"{")
                        ifin = ifin[:-1]
                        gc, adminstatus = adminstatus.split(b"{")
                        adminstatus = adminstatus[:-1]
                        adminstatus = adminstatus.decode("ascii")
                        
                    # Create snmp get commands
                    snmp_base = ("snmp get %s ZhonePrivate " % ip).encode("ascii")

                    # Create lengthy SNMP get commands
                    oml_cmd = snmp_base + b" " + b"ifEntry.ifOperStatus." + ifin + b" " + b"zhoneVdslLineConfProfileEntry.zhoneVdslLineConfTransmissionMode." + ifin + b" " + b"zhoneVdslLineConfProfileEntry.zhoneVdslLineConfLineType." + ifin + b"\n"
                    train_cmd = snmp_base + b"zhoneVdslChanEntry.zhoneVdslChanCurrTxRate." + ifin + b".1" + b" " + b"zhoneVdslChanEntry.zhoneVdslChanCurrTxRate." + ifin + b".2" + b"\n"
                    maxt_snrdn_cmd = snmp_base + b"zhoneVdslPhysEntry.zhoneVdslPhysCurrAttainableRate." + ifin + b".1" + b" " + b"zhoneVdslPhysEntry.zhoneVdslPhysCurrAttainableRate." + ifin + b".2" + b" " + b"zhoneVdslPhysEntry.zhoneVdslPhysCurrSnrMgn." + ifin + b".1" + b"\n"
                    snrup_out_cmd = snmp_base + b"zhoneVdslPhysEntry.zhoneVdslPhysCurrSnrMgn." + ifin + b".2" + b" " + b"zhoneVdslPhysEntry.zhoneVdslPhysCurrOutputPwr." + ifin + b".1" + b" " + b"zhoneVdslPhysEntry.zhoneVdslPhysCurrOutputPwr." + ifin + b".2" + b"\n"
                    lntime_cmd = snmp_base + b"zhoneVdslPhysEntry.zhoneVdslPhysCurrAtn." + ifin + b".1" + b" " + b"zhoneVdslPhysEntry.zhoneVdslPhysCurrAtn." + ifin + b".2" + b" " + b"zhoneDslLineEntry.zhoneDslLineUpTime." + ifin + b"\n"
                    
                    # Get SNMP Stats
                    # Get OperStatus Mode LineType
                    writer.write(oml_cmd)
                    await asyncio.sleep(rt)
                    writer.write(nl)
                    await asyncio.sleep(rt)
                    gc = await reader.readuntil(pl)
                    gc = gc.split(b"\n\r")
                    if len(gc) != 5:
                        raise PortError
                    operstatus = gc[1]
                    mode = gc[2]
                    linetype = gc[3]
                    
                    # Get OperStatus
                    gc, operstatus = operstatus.split(b"Value: ")
                    operstatus = operstatus.decode("ascii")[0]
                    if operstatus == "1":
                        operstatus = "up"
                    elif operstatus == "2":
                        operstatus = "down"
                    elif operstatus == "3":
                        operstatus = "testing"
                    elif operstatus == "4":
                        operstatus = "unknown"
                    elif operstatus == "5":
                        operstatus = "dormant"
                    elif operstatus == "6":
                        operstatus = "notPresent"
                    elif operstatus == "7":
                        operstatus = "lowerLayerDown"
                    else:
                        operstatus = "error"
                    
                    # Get Mode
                    gc, mode = mode.split(b"Value: ")
                    if mode.decode("ascii")[1] == "0":
                        mode = "vdsl2VectAdsl2+Mode"
                    else:
                        mode = mode.decode("ascii")[0]
                        if mode == "1":
                            mode = "autoNegMode"
                        elif mode == "2":
                            mode = "vdslMode"
                        elif mode == "3":
                            mode = "vdsl2Mode"
                        elif mode == "4":
                            mode = "adsl2+Mode"
                        elif mode == "5":
                            mode = "adsl2Mode"
                        elif mode == "6":
                            mode = "gdmtMode"
                        elif mode == "7":
                            mode = "vdsl2adsl2+Mode"
                        elif mode == "8":
                            mode = "vdsl2-vectoring"
                        elif mode == "9":
                            mode = "vdsl2VectVdsl2Mode"
                        else:
                            mode = "unknown"
                            
                    # Get LineType
                    gc, linetype = linetype.split(b"Value: ")
                    linetype = linetype.decode("ascii")[0]
                    if linetype == "1":
                        linetype = "noChannel"
                    elif linetype == "2":
                        linetype = "fastOnly"
                    elif linetype == "3":
                        linetype = "interleavedOnly"
                    elif linetype == "4":
                        linetype = "fastOrInterleaved"
                    elif linetype == "5":
                        linetype = "fastAndInterleaved"
                    else:
                        linetype = "unknown"
                        
                    if operstatus == "up":
                        # Get DnTrain UpTrain
                        writer.write(train_cmd)
                        await asyncio.sleep(rt)
                        writer.write(nl)
                        await asyncio.sleep(rt)
                        gc = await reader.readuntil(pl)
                        gc = gc.split(b"\n\r")
                        if len(gc) != 4:
                            raise PortError
                        dntrain = gc[1]
                        uptrain = gc[2]
                        
                        # Get DnTrain
                        gc, dntrain = dntrain.split(b"Value: ")
                        dntrain, gc = dntrain.split(b" (")
                        dntrain = dntrain.decode("ascii")
                        
                        # Get UpTrain
                        gc, uptrain = uptrain.split(b"Value: ")
                        uptrain, gc = uptrain.split(b" (")
                        uptrain = uptrain.decode("ascii")
                        
                        # Get MaxDnTrain MaxUpTrain DnSNRMgn
                        writer.write(maxt_snrdn_cmd)
                        await asyncio.sleep(rt)
                        writer.write(nl)
                        await asyncio.sleep(rt)
                        gc = await reader.readuntil(pl)
                        gc = gc.split(b"\n\r")
                        if len(gc) != 5:
                            raise PortError
                        maxdntrain = gc[1]
                        maxuptrain = gc[2]
                        dnSNRmgn = gc[3]

                        
                        # Get MaxDnTrain
                        gc, maxdntrain = maxdntrain.split(b"Value: ")
                        maxdntrain, gc = maxdntrain.split(b" (")
                        maxdntrain = maxdntrain.decode("ascii")
                        
                        # Get MaxUpTrain
                        gc, maxuptrain = maxuptrain.split(b"Value: ")
                        maxuptrain, gc = maxuptrain.split(b" (")
                        maxuptrain = maxuptrain.decode("ascii")
                        
                        # Get DnSNRMgn
                        gc, dnSNRmgn = dnSNRmgn.split(b"Value: ")
                        dnSNRmgn, gc = dnSNRmgn.split(b" (")
                        dnSNRmgn = dnSNRmgn.decode("ascii")
                        
                        # Get UpSNRMgn DnOutPwr UpOutPwr
                        writer.write(snrup_out_cmd)
                        await asyncio.sleep(rt)
                        writer.write(nl)
                        await asyncio.sleep(rt)
                        gc = await reader.readuntil(pl)
                        gc = gc.split(b"\n\r")
                        if len(gc) != 5:
                            raise PortError
                        upSNRmgn = gc[1]
                        dnoutpwr = gc[2]
                        upoutpwr = gc[3]

                            
                        # Get UpSNRMgn
                        gc, upSNRmgn = upSNRmgn.split(b"Value: ")
                        upSNRmgn, gc = upSNRmgn.split(b" (")
                        upSNRmgn = upSNRmgn.decode("ascii")
                            
                        # Get DnOutPwr
                        gc, dnoutpwr = dnoutpwr.split(b"Value: ")
                        dnoutpwr, gc = dnoutpwr.split(b" (")
                        dnoutpwr = dnoutpwr.decode("ascii")
                            
                        # Get UpOutPwr
                        gc, upoutpwr = upoutpwr.split(b"Value: ")
                        upoutpwr, gc = upoutpwr.split(b" (")
                        upoutpwr = upoutpwr.decode("ascii")
                        
                        # Get DnLineAtn UpLineAtn UpTime
                        writer.write(lntime_cmd)
                        await asyncio.sleep(rt)
                        writer.write(nl)
                        await asyncio.sleep(rt)
                        gc = await reader.readuntil(pl)
                        gc = gc.split(b"\n\r")
                        if len(gc) != 5:
                            raise PortError
                        dnlineatn = gc[1]
                        uplineatn = gc[2]
                        uptime = gc[3]
                        
                        # Get DnLineAtn
                        gc, dnlineatn = dnlineatn.split(b"Value: ")
                        dnlineatn, gc = dnlineatn.split(b" (")
                        dnlineatn = dnlineatn.decode("ascii")
                        
                        # Get UpLineAtn
                        gc, uplineatn = uplineatn.split(b"Value: ")
                        uplineatn, gc = uplineatn.split(b" (")
                        uplineatn = uplineatn.decode("ascii")
                        
                        # Get UpTime
                        gc, uptime = uptime.split(b"Value: ")
                        uptime = uptime.decode("ascii")[:-3]
                        uptime = uptime.replace(" ", "-")
                    else:
                        dntrain = "0"
                        uptrain = "0"
                        maxdntrain = "0"
                        maxuptrain = "0"
                        dnSNRmgn = "0"
                        upSNRmgn = "0"
                        dnoutpwr = "0"
                        upoutpwr = "0"
                        dnlineatn = "0"
                        uplineatn = "0"
                        uptime = "000-days-00:00:00:00"
                        
                    # Write port info to file
                    log.write("\n" + ip + " " + str(slot) + " " + str(port) + " " + adminstatus + " " + operstatus + " " + mode + " " + linetype + " " + dntrain + " " + uptrain + " " + maxdntrain + " " + maxuptrain + " " + dnSNRmgn + " " + upSNRmgn + " " + dnoutpwr + " " + upoutpwr + " " + dnlineatn + " " + uplineatn + " " + uptime)

                except IfIndexError:
                    print("Exception thrown in device with IP: %s" % ip)
                    print("Return from get if-translate command is not expected length")
                    if adminstatus == "unknown":
                        adminstatus = "error"
                    if operstatus == "unknown":
                        operstatus = "error"
                    if mode == "unknown":
                        mode = "error"
                    if linetype == "unknown":
                        linetype = "error"
                    if dntrain == "unknown":
                        dntrain = "error"
                    if uptrain == "unknown":
                        uptrain = "error"
                    if maxdntrain == "unknown":
                        maxdntrain = "error"
                    if maxuptrain == "unknown":
                        maxuptrain = "error"
                    if dnSNRmgn == "unknown":
                        dnSNRmgn = "error"
                    if upSNRmgn == "unknown":
                        upSNRmgn = "error"
                    if dnoutpwr == "unknown":
                        dnoutpwr = "error"
                    if upoutpwr == "unknown":
                        upoutpwr = "error"
                    if dnlineatn == "unknown":
                        dnlineatn = "error"
                    if uplineatn == "unknown":
                        uplineatn = "error"
                    if uptime == "unknown":
                        uptime = "error"
                    log.write("\n" + ip + " " + str(slot) + " " + str(port) + " " + adminstatus + " " + operstatus + " " + mode + " " + linetype + " " + dntrain + " " + uptrain + " " + maxdntrain + " " + maxuptrain + " " + dnSNRmgn + " " + upSNRmgn + " " + dnoutpwr + " " + upoutpwr + " " + dnlineatn + " " + uplineatn + " " + uptime)
                    continue
                except PortError:
                    print("Exception thrown in device with IP: %s" % ip)
                    print("Return from an snmp get command was not expected length")
                    if adminstatus == "unknown":
                        adminstatus = "error"
                    if operstatus == "unknown":
                        operstatus = "error"
                    if mode == "unknown":
                        mode = "error"
                    if linetype == "unknown":
                        linetype = "error"
                    if dntrain == "unknown":
                        dntrain = "error"
                    if uptrain == "unknown":
                        uptrain = "error"
                    if maxdntrain == "unknown":
                        maxdntrain = "error"
                    if maxuptrain == "unknown":
                        maxuptrain = "error"
                    if dnSNRmgn == "unknown":
                        dnSNRmgn = "error"
                    if upSNRmgn == "unknown":
                        upSNRmgn = "error"
                    if dnoutpwr == "unknown":
                        dnoutpwr = "error"
                    if upoutpwr == "unknown":
                        upoutpwr = "error"
                    if dnlineatn == "unknown":
                        dnlineatn = "error"
                    if uplineatn == "unknown":
                        uplineatn = "error"
                    if uptime == "unknown":
                        uptime = "error"
                    log.write("\n" + ip + " " + str(slot) + " " + str(port) + " " + adminstatus + " " + operstatus + " " + mode + " " + linetype + " " + dntrain + " " + uptrain + " " + maxdntrain + " " + maxuptrain + " " + dnSNRmgn + " " + upSNRmgn + " " + dnoutpwr + " " + upoutpwr + " " + dnlineatn + " " + uplineatn + " " + uptime)
                    continue
                except Exception as e:
                    print("Exception thrown in device with IP: %s" % ip)
                    print(e)
                    ipi['_fip'].append("%s" % ip)
                    return
    except PromptLineError:
        print("Exception thrown in device with IP: %s" % ip)
        print("Prompt Line does not match expected pattern, either something went wrong, or the pattern must be revised.")
        ipi['_fip'].append("%s" % ip)
        return
    except Exception as e:
        print("Exception thrown in device with IP: %s" % ip)
        print(e)
        ipi['_fip'].append("%s" % ip)
        return
    else:
        log.close()
    finally:
        writer.close()

async def q_handler(q, ipi):
    while True:
        if q.empty():
            return
        next = await q.get()
        await connect(next, ipi)
        ipi['cnip'] += 1
        pbp = ipi['cnip'] / int(ipi['nip'])
        pbl = 30
        pb = round(pbp*pbl)
        print("\r", "|" + "#"*pb + "-"*(pbl-pb) + "| " + "%s/%s" % (ipi['cnip'], ipi['nip']))
        sys.stdout.flush()
async def queue(loop):
    q = asyncio.Queue()
    _ip = ['LIST OF IPs']
    ipi = {'nip':str(len(_ip)), 'cnip':0, '_fip':[]}
    for ip in _ip:
        await q.put(ip)
    _active_slot = [loop.create_task(q_handler(q, ipi)) for _ in range(10)]
    await asyncio.wait(_active_slot)
    if len(ipi['_fip']) > 0:
        print("Failed to log devices with the following IPs")
        print(ipi['_fip'])
        ipi['nip'] = str(len(ipi['_fip']))
        ipi['cnip'] = 0
        q = asyncio.Queue()
        for ip in ipi['_fip']:
            ipi['_fip'].remove(ip)
            await q.put(ip)
        _active_slot = [loop.create_task(q_handler(q, ipi)) for _ in range(3)]
        await asyncio.wait(_active_slot)

print("Program started at: %s" % datetime.datetime.now().strftime("%H:%M:%S"))
t = time.time()
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(queue(loop))
    except Exception as e:
        print(e)
    finally:
        loop.close()
print("Program elapsed time: "+ str(datetime.timedelta(seconds=(time.time() - t))))
