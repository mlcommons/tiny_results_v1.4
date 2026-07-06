# -*- coding: utf-8 -*-
"""
Created on Tue Aug 31 10:37:31 2021

@author: dyou
"""

import numpy as np
import matplotlib.pyplot as plt
import pickle
import tensorflow as tf
import argparse
#import keras
from sklearn.metrics import roc_auc_score

import train
import eval_functions_eembc
import keras_model
import json
import logging
from aimet_tensorflow.keras import quantsim
# from aimet_tensorflow.cross_layer_equalization import equalize_model
from aimet_tensorflow.keras.batch_norm_fold import fold_all_batch_norms
# from aimet_tensorflow.bias_correction import QuantParams, BiasCorrectionParams, BiasCorrection
import os


model_name = keras_model.get_model_name()
model_name = "pretrainedResnet_large"

logger = logging.getLogger(__name__)
def load_json(json_path):
    try:
        with open(json_path, "r") as json_file:
            try:
                json_data = json.load(json_file)
                return json_data
            except ValueError as e:
                logger.error("error parsing JSON file: " + json_path + " " + repr(e))
                return []
    except Exception as e:
        logger.error("error opening file: " + json_path + " " + repr(e))

def save_tflite(sess, inputs, outputs, path):
    g = sess.graph
    with g.as_default():
        in_tensor = []
        out_tensor = []
        for i in inputs:
            in_tensor.append(g.get_tensor_by_name(name='%s:0'%i))
        for o in outputs:
            out_tensor.append(g.get_tensor_by_name(name='%s:0'%o))
        converter = tf.lite.TFLiteConverter.from_session(sess, in_tensor, out_tensor)
        tflite_model = converter.convert()
        open(path, "wb").write(tflite_model)

def keras_model_to_tflite(model, path):
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    #converter.optimizations = [tf.lite.Optimize.DEFAULT]
    tflite_model = converter.convert()
    open(path, "wb").write(tflite_model)

def get_quantization_dataset(batch):
    cifar_10_dir = 'cifar-10-batches-py'
    sample_img = []
    sample_labels = []
    train_data, train_filenames, train_labels, test_data, test_filenames, test_labels, label_names = \
        train.load_cifar_10_data(cifar_10_dir)
    print(test_data.shape)
    _idx = np.load(cal_file)
    for i in _idx:
        sample_img.append(np.array(test_data[i], dtype=np.float32))
        sample_labels.append(np.array(test_labels[i], dtype=np.float32))
    return tf.data.Dataset.from_tensor_slices((np.array(sample_img),np.array(sample_labels))).repeat(1).batch(batch, drop_remainder=True)

def eval_quant_func(model, iterations):
    num_classes = 10
    outputs = np.zeros((0, num_classes))
    labels = np.array([])
    idex = 0
    dataset = get_quantization_dataset(batch=1)
    for img_batch, label_batch in dataset:
        if iterations != -1 and idex >= iterations:
            break
        out = model(img_batch, training=False)
        outputs = np.vstack((outputs, out.numpy()))
        labels = np.hstack((labels, np.argmax(label_batch.numpy(), axis=1)))
        idex += 1
    accuracy_eembc = eval_functions_eembc.calculate_accuracy(outputs, labels)
    print("accuracy on energy: %s" % (str(accuracy_eembc)))
    return accuracy_eembc

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
    '--cal_file',
    type=str,
    default="calibration_samples_idxs.npy",
    help="calibration data index")
    parser.add_argument(
    '--model_info',
    type=str,
    default="model_info.json",
    help="model infomation")
    parser.add_argument(
    '--quantsim_config',
    type=str,
    default="config_for_eai.json",
    help="quantization simulation config")
    parser.add_argument(
    '--params',
    type=str,
    default="trained_models/pretrainedResnet_large.h5",
    help="model parameter")
    args=parser.parse_args()

    cal_file = args.cal_file
    model_config = args.model_info
    quantsim_config_file = args.quantsim_config
    h5_model = args.params
    
    cifar_10_dir = 'cifar-10-batches-py'
    train_data, train_filenames, train_labels, test_data, test_filenames, test_labels, label_names = \
        train.load_cifar_10_data(cifar_10_dir)
    print("Test data: ", test_data.shape)
    print("Test filenames: ", test_filenames.shape)
    print("Test labels: ", test_labels.shape)
    print("Label names: ", label_names.shape)
    label_classes = np.argmax(test_labels,axis=1)
    print("Label classes: ", label_classes.shape)

    # tf.reset_default_graph()
    # tf.keras.backend.set_learning_phase(0)
    # sess = tf.Session()
    # tf.keras.backend.set_session(sess)
    model = tf.keras.models.load_model('trained_models/' + model_name + '.h5', compile=False)
    # model = keras_model.resnet_v1_eembc(conv_filters=26)
    # model.load_weights(h5_model)

    model_config = load_json(model_config)
    input_op_name = model_config["input_node"]
    output_op_name =model_config["output_node"]

    # sess, folded_pairs = fold_all_batch_norms(sess, input_op_name, output_op_name)
    _, model = fold_all_batch_norms(model)
    # save_tflite(sess, input_op_name, output_op_name, "source_model.tflite")    
    
    sim = quantsim.QuantizationSimModel(model=model,
                                    # starting_op_names=input_op_name,
                                    # output_op_names=output_op_name,
                                    quant_scheme='tf',
                                    default_output_bw=8,
                                    default_param_bw=8,
                                    config_file=quantsim_config_file)
    sim.compute_encodings(eval_quant_func, forward_pass_callback_args=500)
    eval_quant_func(sim, -1)
    sim.export("results","ic_tf_sym_w8_a8")

    # save_tflite(sim.session, input_op_name, output_op_name, "source_model_aimet.tflite")   

