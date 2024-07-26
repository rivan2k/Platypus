import urllib3
import serial
import redfish
import requests
import threading
import os
from http.server import SimpleHTTPRequestHandler, HTTPServer
import asyncio
import time





# Suppress the warning for unverified HTTPS requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)



async def bmc_update(bmc_user, bmc_pass, bmc_ip, fw_content, callback_progress, callback_output):
    callback_output("Initializing Red Fish client...")
    redfish_client = redfish.redfish_client(base_url=f"https://{bmc_ip}", username=bmc_user, password=bmc_pass)
    callback_progress(0.25)
    
    try:
        await asyncio.to_thread(redfish_client.login)
        update_service = redfish_client.get("/redfish/v1/UpdateService")
        if update_service.status != 200:
            callback_output("Failed to find the update service.")
            return

        callback_progress(0.50)
        callback_output("Logged in.")

        update_service_url = update_service.dict["@odata.id"]

        # Firmware update
        headers = {"Content-Type": "application/octet-stream"}
        callback_output("Sending update request...")
        response = await asyncio.to_thread(redfish_client.post, f"{update_service_url}/update", body=fw_content, headers=headers)
        callback_progress(0.75)

        if response.status in [200, 202]:
            callback_output(f"Update initiated successfully: {response.text}")
            task_url = response.dict["@odata.id"]
            await monitor_task(redfish_client, task_url, callback_output, callback_progress)
        else:
            callback_output(f"Failed to initiate firmware update. Response code: {response.status}")
    except Exception as e:
        callback_output(f"Error: {e}")
    finally:
        await asyncio.to_thread(redfish_client.logout)
    
    await asyncio.sleep(5)
    callback_progress(0)



async def monitor_task(redfish_client, task_url, callback_output, callback_progress):
    while True:
        task_response = await asyncio.to_thread(redfish_client.get, task_url)
        if task_response.status != 200:
            callback_output("Failed to get task status.")
            break

        task_status = task_response.dict["TaskState"]
        callback_output(f"Task status: {task_status}")

        if task_status in ["Completed", "Exception", "Killed"]:
            if task_status == 'Completed':
                callback_progress(1)
            callback_output(f"Task completed with status: {task_status}")
            break

        await asyncio.sleep(5)



def bmc_info(bmc_user, bmc_pass, bmc_ip):
    try:
        # Initialize the Redfish client
        redfish_client = redfish.redfish_client(base_url=f"https://{bmc_ip}", username=bmc_user, password=bmc_pass)
        
        # Login to the Redfish service
        redfish_client.login(auth="session")
        
        # Fetch the BMC information
        response = redfish_client.get("/redfish/v1/Managers/bmc")
        
        if response.status == 200:
            bmc_info = response.dict
            #print(bmc_info)
            return(bmc_info)
        else:
            print(f"Failed to fetch BMC information. Status code: {response.status}")
            return None
        
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return None
    finally:
        # Logout to release the session
        redfish_client.logout()





async def set_ip(bmc_ip, bmc_user, bmc_pass, callback_progress, callback_output):
    ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)
    user = f"{bmc_user}\n"
    passw = f"{bmc_pass}\n"
    command = f"ifconfig eth0 up {bmc_ip}\n"

    callback_progress(0.25)
    callback_output("Running...")

    try:
        ser.flushInput()
        ser.write(b"\n")
        # Check if already logged in by looking for the command prompt
        initial_prompt = ser.read_all().decode('utf-8')
        print(f'Prompt: {initial_prompt}')
            
        if '#' not in initial_prompt:
            # Not logged in, proceed with login
            ser.write(user.encode('utf-8'))
            await asyncio.sleep(2)
            ser.write(passw.encode('utf-8'))
            await asyncio.sleep(2)
        
        callback_progress(0.5)
        callback_output("Logged in.")

        # Send the command to set the IP
        ser.write(command.encode('utf-8'))

        # Reading the response from the command
        response = ser.read_until(b'\n')
        callback_output(response.decode('utf-8'))

        callback_progress(0.75)
        callback_output("Setting IP...")
    except Exception as e:
        callback_output(f"Error: {e}")
    
    ser.close()
    callback_progress(1)
    callback_output("IP set successfully.")
    await asyncio.sleep(5)
    callback_progress(0)



server_running = False

def start_server(directory, port, callback_output):
    global server_running
    if server_running:
        callback_output("Server is already running.")
        return

    os.chdir(directory)
    handler = SimpleHTTPRequestHandler
    httpd = HTTPServer(('0.0.0.0', port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    server_running = True
    callback_output(f"Serving files from {directory} on port {port}")



async def flasher(bmc_user, bmc_pass, flash_file, my_ip, callback_progress, callback_output):
    directory = os.path.dirname(flash_file)
    file_name = os.path.basename(flash_file)
    port = 5000

    start_server(directory, port, callback_output)
    callback_progress(0.2)

    ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)
    user = f"{bmc_user}\n"
    passw = f"{bmc_pass}\n"

    try:
        initial_prompt = await asyncio.to_thread(ser.read_until, b'# ')
            

        ser.write(user.encode('utf-8'))
        await asyncio.sleep(2)
        ser.write(passw.encode('utf-8'))
        await asyncio.sleep(5)
        
        callback_progress(0.4)

        url = f"http://{my_ip}:{port}/{file_name}"
        curl_command = f"curl -o {file_name} {url}\n"
        ser.write(curl_command.encode('utf-8'))
        await asyncio.sleep(5)
        callback_output('Curl command sent.')

        callback_progress(0.6)

        command = "echo 0 > /sys/block/mmcblk0boot0/force_ro\n"
        ser.write(command.encode('utf-8'))
        await asyncio.sleep(4)
        callback_output('Changed MMC to RW')

        callback_progress(0.8)

        command = f'dd if={file_name} of=/dev/mmcblk0boot0 bs=512 seek=256\n'
        ser.write(command.encode('utf-8'))
        await asyncio.sleep(7)
        callback_output("Flashing complete")
        callback_progress(1)
    except serial.SerialException as e:
        callback_output(f"Serial Error: {e}")
    finally:
        ser.close()
    callback_progress(0)



async def reset_ip(bmc_user, bmc_pass, bmc_ip, callback_progress, callback_output):
    callback_progress(0.4)
    url = f"https://{bmc_ip}/redfish/v1/Managers/bmc/Actions/Manager.ResetToDefaults"
    headers = {"Content-Type": "application/json"}
    payload = {"ResetToDefaultsType": "ResetAll"}
    callback_progress(0.8)
    try:
        response = await asyncio.to_thread(requests.post, url, json=payload, headers=headers, auth=(bmc_user, bmc_pass), verify=False)
        if response.status_code == 200:
            callback_output("BMC reset to factory defaults successfully.")
            callback_progress(1)
        else:
            callback_output("Failed to reset BMC. Response code:", response.status_code)
            callback_output(response.json())
    except Exception as e:
        callback_output("Error occurred:", e)
           
    callback_progress(0)

   

def read_serial_data(ser, command, delay=2):
    """Function to handle blocking serial operations."""
    try:
        # Give some time for the serial device to be ready
        time.sleep(delay)
        
        # Write the command to the serial port
        ser.write(command.encode('utf-8'))
        time.sleep(2)  # Wait for the response
        
        # Read the data from the serial port
        response = ser.read_all().decode('utf-8')
        return response
    except Exception as e:
        print(f"Error reading serial data: {e}")
        return ""



async def grab_ip(bmc_user, bmc_pass):
    ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)
    user = f"{bmc_user}\n"
    passw = f"{bmc_pass}\n"
    command = "ifconfig eth0\n"

    try:
        # Login and execute the command
        await asyncio.to_thread(ser.write, b'\n')
        await asyncio.to_thread(ser.write, user.encode('utf-8'))
        await asyncio.sleep(2)
        await asyncio.to_thread(ser.write, passw.encode('utf-8'))
        await asyncio.sleep(2)
        
        # Execute command and read response
        response = await asyncio.to_thread(read_serial_data, ser, command)
        print(f"Response: {response}")

        # Parse the response to find the IP address
        lines = response.split('\n')
        for line in lines:
            if 'inet ' in line and 'inet6' not in line:
                part = line.split(':')[1]
                ip_address = part.split()[0]
                print(ip_address)
        return ip_address
    except Exception as e:
        print(f"Error: {e}")
        return None
    finally:
        ser.close()



async def flash_emmc(bmc_user, bmc_pass, bmc_ip, flash_file, my_ip, callback_output):
    directory = os.path.dirname(flash_file)
    file_name = os.path.basename(flash_file)
    port = 80
    command = 'reboot\n'

    start_server(directory, port, callback_output)

    ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)
    user = f"{bmc_user}\n"
    passw = f"{bmc_pass}\n"

    try:
        ser.write(b'\n')
        await asyncio.sleep(2)
        ser.write(user.encode('utf-8'))
        await asyncio.sleep(2)
        ser.write(passw.encode('utf-8'))
        await asyncio.sleep(5)
        
        ser.write(command.encode('utf-8'))
        await asyncio.sleep(5)

        # while True:
        #     line = ser.readline().decode('utf-8', errors='replace')
        #     print(line)
        #     if 'Hit any key' in line:
        #         ser.write(b'\n')
        #         break
        await asyncio.sleep(2)
        ser.write(f'setenv ipaddr {bmc_ip}\n'.encode('utf-8'))
        await asyncio.sleep(2)
        ser.write(f'wget ${{loadaddr}} {my_ip}:/obmc-rescue-image-snuc-nanobmc.itb; bootm\n'.encode('utf-8'))
        await asyncio.sleep(35)
        command = f'ifconfig eth0 up {bmc_ip}\n'
        ser.write(command.encode('utf-8'))
        await asyncio.sleep(2)
        curl_command = f"curl -o obmc-phosphor-image-snuc-nanobmc.wic.xz {my_ip}/obmc-phosphor-image-snuc-nanobmc.wic.xz\n"
        ser.write(curl_command.encode('utf-8'))
        await asyncio.sleep(5)
        curl_command = f'curl -o obmc-phosphor-image-snuc-nanobmc.wic.bmap {my_ip}/obmc-phosphor-image-snuc-nanobmc.wic.bmap\n'
        await asyncio.sleep(5)
        ser.write(curl_command.encode('utf-8'))
        await asyncio.sleep(5)
        ser.write(f'bmaptool copy obmc-phosphor-image-snuc-nanobmc.wic.xz /dev/mmcblk0\n'.encode('utf-8'))
        await asyncio.sleep(30)
        print('done')

    except Exception as e:
        print(f"Error: {e}")
        return None
    finally:
        ser.close()
    
